"""
Router /v2/chat — version mới dùng orchestrator để điều phối
math RAG + từ điển Tày/Nùng cho cùng một câu hỏi.
Hỗ trợ conversation_id để lưu context lịch sử.
"""

import asyncio
import json
import logging

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.dependencies import get_optional_user
from backend.services.compactor import compact_conversation, should_compact
from backend.services.content_safety import is_meaningful_question, is_safe
from backend.services.gemini import ask_gemini, stream_gemini
from backend.services.orchestrator import QueryType, orchestrate
from backend.services.supabase_client import (
    create_conversation,
    get_or_create_session,
    get_recent_history,
    save_conv_messages,
    save_messages,
)

load_dotenv()
router = APIRouter()
log = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None   # null = tạo conversation mới
    grade: int = 0
    language: str = "vi"
    mode: str                             # "student" | "teacher"


class VocabEntry(BaseModel):
    vi: str
    tay: str | None = None
    nung: str | None = None


class ChatResponse(BaseModel):
    answer: str
    source: str
    score: float | None = None
    intent: str | None = None
    steps: list[str] | None = None
    vocab: list[VocabEntry] | None = None
    grade: int | None = None


# ---------------------------------------------------------------------------
# Context formatters
# ---------------------------------------------------------------------------

def _format_math_context(contexts: list[dict]) -> str:
    parts: list[str] = []
    for ctx in contexts:
        content = (ctx.get("content") or "").strip()
        if not content:
            continue
        title = ctx.get("title") or ""
        grade = ctx.get("grade")
        header_bits = []
        if title:
            header_bits.append(title)
        if grade:
            header_bits.append(f"lớp {grade}")
        header = f"[{' — '.join(header_bits)}]\n" if header_bits else ""
        parts.append(f"{header}{content}")
    return "\n---\n".join(parts)


def _format_dict_context(contexts: list[dict]) -> str:
    parts: list[str] = []
    for ctx in contexts:
        vi = (ctx.get("vi") or "").strip()
        tay_variants = ctx.get("tay_variants") or []
        nung_variants = ctx.get("nung_variants") or []
        direction = ctx.get("direction") or ""

        tay_str = (
            ", ".join(tay_variants)
            if isinstance(tay_variants, list)
            else str(tay_variants)
        )
        nung_str = (
            ", ".join(nung_variants)
            if isinstance(nung_variants, list)
            else str(nung_variants)
        )

        if direction == "tay_to_vi" and not tay_str:
            content = (ctx.get("content") or "").strip()
            if content:
                parts.append(content)
                continue

        line_parts = []
        if vi:
            line_parts.append(f"Việt: {vi}")
        if tay_str:
            line_parts.append(f"Tày: {tay_str}")
        if nung_str:
            line_parts.append(f"Nùng: {nung_str}")
        if not line_parts:
            content = (ctx.get("content") or "").strip()
            if content:
                parts.append(content)
                continue

        line = "; ".join(line_parts)
        dialect = (ctx.get("dialect_note") or "").strip()
        if dialect:
            line += f"  (Lưu ý vùng/phương ngữ: {dialect})"
        parts.append(line)

    return "\n".join(parts)


def _build_vocab(dict_contexts: list[dict]) -> list[VocabEntry]:
    seen: set[str] = set()
    entries: list[VocabEntry] = []
    for ctx in dict_contexts:
        vi = (ctx.get("vi") or "").strip()
        if not vi or vi in seen:
            continue
        if (ctx.get("direction") or "") == "tay_to_vi":
            continue
        seen.add(vi)
        tay_variants = ctx.get("tay_variants") or []
        nung_variants = ctx.get("nung_variants") or []
        tay_str = ", ".join(tay_variants) if isinstance(tay_variants, list) and tay_variants else None
        nung_str = ", ".join(nung_variants) if isinstance(nung_variants, list) and nung_variants else None
        entries.append(VocabEntry(vi=vi, tay=tay_str, nung=nung_str))
    return entries


def _build_rag_context(result) -> str:
    context_parts: list[str] = []
    if result.math_context:
        math_str = _format_math_context(result.math_context)
        if math_str:
            context_parts.append("Kiến thức Toán:\n" + math_str)
    if result.dict_context:
        dict_str = _format_dict_context(result.dict_context)
        if dict_str:
            context_parts.append("Từ điển Tày/Nùng:\n" + dict_str)
    return "\n\n".join(context_parts)


def _build_history_context(messages: list[dict], compact_summary: str | None) -> str:
    parts: list[str] = []
    if compact_summary:
        parts.append(f"[Tóm tắt cuộc hội thoại trước]: {compact_summary}")
    if messages:
        history_lines = []
        for msg in messages:
            label = "Học sinh" if msg["role"] == "user" else "Trợ lý"
            content = msg["content"][:500]
            history_lines.append(f"{label}: {content}")
        parts.append("[Lịch sử cuộc hội thoại gần đây]\n" + "\n".join(history_lines))
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Legacy history save (for unauthenticated / session-based flow)
# ---------------------------------------------------------------------------

async def _save_history_legacy(
    user_id: str,
    mode: str,
    user_msg: str,
    assistant_msg: str,
    query_type: str,
    source: str,
) -> None:
    try:
        session_id = await get_or_create_session(user_id, mode)
        await save_messages(session_id, user_msg, assistant_msg, query_type, source)
    except Exception as exc:
        log.warning("[CHAT_V2] legacy history save failed: %s", exc)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/")
async def chat(
    req: ChatRequest,
    user_id: str | None = Depends(get_optional_user),
):
    log.info(
        "[CHAT_V2] message=%r  conv=%s  grade=%d  lang=%s  mode=%s",
        req.message, req.conversation_id, req.grade, req.language, req.mode,
    )

    # 1. Safety checks
    if not is_safe(req.message):
        log.info("[CHAT_V2] → BLOCKED by content_safety")

        async def _safety_stream():
            yield _sse({"type": "metadata", "source": "safety", "conversation_id": None})
            yield _sse({"type": "chunk", "text": "Câu hỏi không phù hợp."})
            yield _sse({"type": "done"})

        return StreamingResponse(_safety_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    if not is_meaningful_question(req.message):
        log.info("[CHAT_V2] → BLOCKED by is_meaningful_question")

        async def _unclear_stream():
            yield _sse({"type": "metadata", "source": "safety", "conversation_id": None})
            yield _sse({"type": "chunk", "text": "Cô chưa hiểu câu hỏi này. Con hãy hỏi về bài Toán hoặc môn học nhé!"})
            yield _sse({"type": "done"})

        return StreamingResponse(_unclear_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    # 2. Conversation management (authenticated users only)
    conversation_id = req.conversation_id
    history_context = ""
    message_count = 0

    if user_id:
        try:
            if not conversation_id:
                conv = await create_conversation(user_id, req.mode)
                conversation_id = conv["id"]
                log.info("[CHAT_V2] Created new conversation %s", conversation_id)

            hist = await get_recent_history(conversation_id, limit=20)
            history_context = _build_history_context(
                hist.get("messages", []),
                hist.get("compact_summary"),
            )
            message_count = hist.get("message_count", 0)
        except Exception as exc:
            log.warning("[CHAT_V2] Conversation management error: %s", exc)
            conversation_id = None

    # 3. Orchestrate
    result = await orchestrate(
        req.message,
        grade=req.grade,
        language=req.language,
        mode=req.mode,
    )
    log.info(
        "[CHAT_V2] type=%s  status=%s  has_math=%s  has_dict=%s",
        result.query_type.value,
        result.retrieval_status,
        bool(result.math_context),
        bool(result.dict_context),
    )

    # 4. Rule Engine shortcut
    if (
        result.query_type == QueryType.MATH_CALCULATE
        and result.math_result is not None
        and result.math_result.ok
    ):
        mr = result.math_result
        log.info("[CHAT_V2] → rule_engine  answer=%r", mr.answer)

        async def _rule_stream():
            yield _sse({
                "type": "metadata",
                "source": "rule_engine",
                "intent": mr.formula_key,
                "steps": mr.steps,
                "conversation_id": conversation_id,
            })
            yield _sse({"type": "chunk", "text": mr.formula})
            yield _sse({"type": "done"})
            if user_id and conversation_id:
                auto_title = None
                if message_count == 0:
                    auto_title = " ".join(req.message.split()[:5])[:30]
                asyncio.create_task(save_conv_messages(
                    conversation_id, req.message, mr.formula,
                    result.query_type.value, "rule_engine",
                    auto_title=auto_title, current_count=message_count,
                ))

        return StreamingResponse(_rule_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    # 5. Stream Gemini với context RAG + history
    rag_context = _build_rag_context(result)
    if history_context and rag_context:
        full_context = history_context + "\n\n" + rag_context
    elif history_context:
        full_context = history_context
    else:
        full_context = rag_context

    vocab_list = _build_vocab(result.dict_context) if result.dict_context else []
    log.info(
        "[CHAT_V2] → stream_gemini  context_len=%d  type=%s",
        len(full_context),
        result.query_type.value,
    )

    async def _gemini_stream():
        full_text: list[str] = []
        yield _sse({
            "type": "metadata",
            "source": result.query_type.value,
            "intent": result.math_result.formula_key if result.math_result else None,
            "vocab": [{"vi": v.vi, "tay": v.tay, "nung": v.nung} for v in vocab_list] if vocab_list else None,
            "conversation_id": conversation_id,
        })
        try:
            async for chunk in stream_gemini(
                prompt=req.message,
                context=full_context,
                grade=req.grade,
                language=req.language,
                role=req.mode,
            ):
                full_text.append(chunk)
                yield _sse({"type": "chunk", "text": chunk})
        except Exception as e:
            log.error("[CHAT_V2] stream_gemini error: %s", e)
            yield _sse({"type": "error", "message": "INTERNAL_ERROR"})
        yield _sse({"type": "done"})
        if user_id and conversation_id:
            assistant_text = "".join(full_text)
            auto_title = None
            if message_count == 0:
                auto_title = " ".join(req.message.split()[:5])[:30]
            asyncio.create_task(save_conv_messages(
                conversation_id, req.message, assistant_text,
                result.query_type.value, result.query_type.value,
                auto_title=auto_title, current_count=message_count,
            ))
            asyncio.create_task(_maybe_compact(conversation_id))

    return StreamingResponse(_gemini_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


async def _maybe_compact(conversation_id: str) -> None:
    try:
        if await should_compact(conversation_id):
            asyncio.create_task(compact_conversation(conversation_id))
    except Exception as exc:
        log.warning("[CHAT_V2] compact check failed for %s: %s", conversation_id, exc)
