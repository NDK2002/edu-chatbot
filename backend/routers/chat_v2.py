"""
Router /v2/chat — version mới dùng orchestrator để điều phối
math RAG + từ điển Tày/Nùng cho cùng một câu hỏi.

ChatRequest / ChatResponse giữ nguyên schema như chat.py v1.
"""

import json
import logging

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.services.content_safety import is_meaningful_question, is_safe
from backend.services.gemini import ask_gemini, stream_gemini
from backend.services.orchestrator import QueryType, orchestrate

load_dotenv()
router = APIRouter()
log = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    grade: int = 0          # 0 = no grade filter (search all grades 1–5)
    language: str = "vi"    # "vi" | "tay_nung"
    mode: str               # "student" | "teacher"


class VocabEntry(BaseModel):
    vi: str
    tay: str | None = None
    nung: str | None = None


class ChatResponse(BaseModel):
    answer: str
    source: str             # "rule_engine" | "vector" | "llm" | "safety"
    score: float | None = None
    intent: str | None = None
    steps: list[str] | None = None
    vocab: list[VocabEntry] | None = None
    grade: int | None = None


# ---------------------------------------------------------------------------
# Helpers: build context string cho Gemini
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

        # Tày → Việt: payload có field 'tay' (đơn) thay vì tay_variants
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


def _build_context(result) -> str:
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


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/")
async def chat(req: ChatRequest):
    log.info(
        "[CHAT_V2] message=%r  grade=%d  lang=%s  mode=%s",
        req.message,
        req.grade,
        req.language,
        req.mode,
    )

    # 1. Safety — still SSE so frontend parser stays consistent
    if not is_safe(req.message):
        log.info("[CHAT_V2] → BLOCKED by content_safety")

        async def _safety_stream():
            yield _sse({"type": "metadata", "source": "safety"})
            yield _sse({"type": "chunk", "text": "Câu hỏi không phù hợp."})
            yield _sse({"type": "done"})

        return StreamingResponse(_safety_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    if not is_meaningful_question(req.message):
        log.info("[CHAT_V2] → BLOCKED by is_meaningful_question")

        async def _unclear_stream():
            yield _sse({"type": "metadata", "source": "safety"})
            yield _sse({"type": "chunk", "text": "Cô chưa hiểu câu hỏi này. Con hãy hỏi về bài Toán hoặc môn học nhé!"})
            yield _sse({"type": "done"})

        return StreamingResponse(_unclear_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    # 2. Orchestrate
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

    # 3. Rule Engine shortcut — wrap in SSE for consistent frontend handling
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
            })
            yield _sse({"type": "chunk", "text": mr.formula})
            yield _sse({"type": "done"})

        return StreamingResponse(_rule_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    # 4. Stream Gemini với context tổng hợp
    context = _build_context(result)
    vocab_list = _build_vocab(result.dict_context) if result.dict_context else []
    log.info(
        "[CHAT_V2] → stream_gemini  context_len=%d  type=%s",
        len(context),
        result.query_type.value,
    )

    async def _gemini_stream():
        yield _sse({
            "type": "metadata",
            "source": result.query_type.value,
            "intent": result.math_result.formula_key if result.math_result else None,
            "vocab": [{"vi": v.vi, "tay": v.tay, "nung": v.nung} for v in vocab_list] if vocab_list else None,
        })
        try:
            async for chunk in stream_gemini(
                prompt=req.message,
                context=context,
                grade=req.grade,
                language=req.language,
                role=req.mode,
            ):
                yield _sse({"type": "chunk", "text": chunk})
        except Exception as e:
            log.error("[CHAT_V2] stream_gemini error: %s", e)
            yield _sse({"type": "error", "message": "INTERNAL_ERROR"})
        yield _sse({"type": "done"})

    return StreamingResponse(_gemini_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)
