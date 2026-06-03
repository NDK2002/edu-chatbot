"""
Router /v2/chat — version mới dùng orchestrator để điều phối
math RAG + từ điển Tày/Nùng cho cùng một câu hỏi.
Hỗ trợ conversation_id để lưu context lịch sử.
"""

import asyncio
import json
import logging
import re

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.dependencies import get_optional_user
from backend.services.compactor import compact_conversation, should_compact
from backend.services.content_safety import is_harmful_content, is_injection_attempt, is_meaningful_question
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
        tay = (ctx.get("tay") or "").strip()
        nung = (ctx.get("nung") or "").strip()
        direction = ctx.get("direction") or ""

        if direction == "tay_vi" and not tay:
            content = (ctx.get("content") or "").strip()
            if content:
                parts.append(content)
                continue

        line_parts = []
        if vi:
            line_parts.append(f"Việt: {vi}")
        if tay:
            line_parts.append(f"Tày: {tay}")
        if nung:
            line_parts.append(f"Nùng: {nung}")
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
        direction = ctx.get("direction") or ""
        tay_raw = (ctx.get("tay") or "").strip()
        if direction == "tay_vi":
            # Bỏ chỉ số đồng âm "(2)" của tay headword rồi dùng làm bản dịch
            tay_clean = re.sub(r"\s*\(\d+\)\s*$", "", tay_raw).strip()
            if not tay_clean:
                continue
            seen.add(vi)
            entries.append(VocabEntry(vi=vi, tay=tay_clean, nung=None))
        else:
            seen.add(vi)
            nung = (ctx.get("nung") or "").strip()
            entries.append(VocabEntry(vi=vi, tay=tay_raw or None, nung=nung or None))
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
    if is_injection_attempt(req.message):
        log.warning("[CHAT_V2] → BLOCKED prompt injection attempt: %r", req.message[:120])

        async def _injection_stream():
            yield _sse({"type": "metadata", "source": "safety", "conversation_id": None})
            yield _sse({"type": "chunk", "text": "Cô chỉ có thể giúp con học Toán và tra từ Tày/Nùng thôi nhé! 😊"})
            yield _sse({"type": "done"})

        return StreamingResponse(_injection_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    if is_harmful_content(req.message):
        log.info("[CHAT_V2] → BLOCKED harmful content")

        async def _safety_stream():
            yield _sse({"type": "metadata", "source": "safety", "conversation_id": None})
            yield _sse({"type": "chunk", "text": "Câu hỏi không phù hợp. Con hãy hỏi về bài học nhé!"})
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

    # 4. Rule Engine shortcut — tính đúng, Gemini diễn đạt thân thiện
    if (
        result.query_type == QueryType.MATH_CALCULATE
        and result.math_result is not None
        and result.math_result.ok
    ):
        mr = result.math_result
        log.info("[CHAT_V2] → rule_engine  answer=%r", mr.answer)

        # Vocab (dùng chung logic với nhánh Gemini)
        rule_vocab_list = (
            _build_vocab(result.dict_context)
            if result.dict_context and result.best_dict_rerank >= 0.10
            else []
        )
        rule_vocab_data = (
            [{"vi": v.vi, "tay": v.tay, "nung": v.nung} for v in rule_vocab_list]
            if rule_vocab_list else None
        )

        # Context cho Gemini: kết quả chính xác từ Rule Engine + từ điển (nếu có)
        steps_str = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(mr.steps))
        explain_parts = [
            "⚠️ KẾT QUẢ ĐÃ ĐƯỢC HỆ THỐNG TÍNH CHÍNH XÁC — KHÔNG TỰ TÍNH LẠI SỐ:",
            f"Công thức: {mr.formula}",
            f"Các bước:\n{steps_str}",
            f"Đáp án: {mr.answer}",
            "",
            "Nhiệm vụ: Diễn đạt lại từng bước trên bằng tiếng Việt đơn giản, thân thiện với học sinh tiểu học.",
            "Chỉ dùng đúng các số và bước giải đã ghi — tuyệt đối không tự tính lại.",
        ]
        if result.dict_context and result.best_dict_rerank >= 0.10:
            dict_str = _format_dict_context(result.dict_context)
            if dict_str:
                explain_parts += ["", "Từ điển Tày/Nùng:", dict_str]
        else:
            explain_parts.append("\n⚠️ Không có dữ liệu từ điển Tày/Nùng. KHÔNG tạo bảng Từ cần nhớ.")
        rule_explain_context = "\n".join(explain_parts)

        async def _rule_stream():
            full_text: list[str] = []
            yield _sse({
                "type": "metadata",
                "source": "rule_engine",
                "intent": mr.formula_key,
                "steps": mr.steps,
                "vocab": rule_vocab_data,
                "conversation_id": conversation_id,
            })
            try:
                async for chunk in stream_gemini(
                    prompt=req.message,
                    context=rule_explain_context,
                    grade=req.grade,
                    language=req.language,
                    role=req.mode,
                ):
                    full_text.append(chunk)
                    yield _sse({"type": "chunk", "text": chunk})
            except Exception as exc:
                log.error("[CHAT_V2] rule_engine explain error: %s", exc)
                # Fallback: hiển thị trực tiếp formula + steps
                fallback = mr.formula + "\n" + "\n".join(mr.steps)
                full_text.append(fallback)
                yield _sse({"type": "chunk", "text": fallback})
            if user_id and conversation_id:
                assistant_text = "".join(full_text)
                auto_title = None
                if message_count == 0:
                    auto_title = " ".join(req.message.split()[:5])[:30]
                try:
                    await save_conv_messages(
                        conversation_id, req.message, assistant_text,
                        result.query_type.value, "rule_engine",
                        auto_title=auto_title, current_count=message_count,
                        steps=mr.steps or None,
                        vocab=rule_vocab_data,
                    )
                except Exception as exc:
                    log.warning("[CHAT_V2] rule_engine save failed: %s", exc)
            yield _sse({"type": "done"})

        return StreamingResponse(_rule_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    # 5. Stream Gemini với context RAG + history
    rag_context = _build_rag_context(result)
    if history_context and rag_context:
        full_context = history_context + "\n\n" + rag_context
    elif history_context:
        full_context = history_context
    else:
        full_context = rag_context

    # Chỉ show vocab card khi dict retrieval thực sự có kết quả liên quan
    vocab_list = (
        _build_vocab(result.dict_context)
        if result.dict_context and result.best_dict_rerank >= 0.10
        else []
    )
    if not vocab_list and not result.dict_context:
        no_dict_note = "\n⚠️ Không có dữ liệu từ điển Tày/Nùng cho câu hỏi này. Không tạo bảng Từ cần nhớ."
        full_context = (full_context + no_dict_note) if full_context else no_dict_note
    log.info(
        "[CHAT_V2] → stream_gemini  context_len=%d  type=%s",
        len(full_context),
        result.query_type.value,
    )

    vocab_data = [{"vi": v.vi, "tay": v.tay, "nung": v.nung} for v in vocab_list] if vocab_list else None

    async def _gemini_stream():
        full_text: list[str] = []
        yield _sse({
            "type": "metadata",
            "source": result.query_type.value,
            "intent": result.math_result.formula_key if result.math_result else None,
            "vocab": vocab_data,
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
        if user_id and conversation_id:
            assistant_text = "".join(full_text)
            auto_title = None
            if message_count == 0:
                auto_title = " ".join(req.message.split()[:5])[:30]
            try:
                await save_conv_messages(
                    conversation_id, req.message, assistant_text,
                    result.query_type.value, result.query_type.value,
                    auto_title=auto_title, current_count=message_count,
                    vocab=vocab_data,
                )
            except Exception as exc:
                log.warning("[CHAT_V2] gemini save failed: %s", exc)
            asyncio.create_task(_maybe_compact(conversation_id))
        yield _sse({"type": "done"})

    return StreamingResponse(_gemini_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


async def _maybe_compact(conversation_id: str) -> None:
    try:
        if await should_compact(conversation_id):
            asyncio.create_task(compact_conversation(conversation_id))
    except Exception as exc:
        log.warning("[CHAT_V2] compact check failed for %s: %s", conversation_id, exc)
