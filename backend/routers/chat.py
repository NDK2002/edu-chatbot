import logging
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.content_safety import is_harmful_content, is_injection_attempt, is_meaningful_question
from backend.services.intent_detector import detect, solve
from backend.services.vector_search import search
from backend.services.gemini import ask_gemini
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()
log = logging.getLogger(__name__)

SCORE_THRESHOLD = float(os.getenv("VECTOR_SCORE_THRESHOLD", 0.70))


class ChatRequest(BaseModel):
    message: str
    grade: int = 0  # 0 = no grade filter (search all grades 1–5)
    language: str = "vi"  # "vi" | "tay_nung"
    mode: str  # "student" | "teacher"


class VocabEntry(BaseModel):
    vi: str
    tay: str | None = None
    nung: str | None = None


class ChatResponse(BaseModel):
    answer: str
    source: str  # "rule_engine" | "vector" | "llm" | "safety"
    score: float | None = None
    intent: str | None = None  # formula_key nếu đi qua Rule Engine
    steps: list[str] | None = None
    vocab: list[VocabEntry] | None = None
    grade: int | None = None


@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest):
    log.info(
        "[CHAT] message=%r  grade=%d  lang=%s", req.message, req.grade, req.language
    )

    # 1. Safety check
    if is_injection_attempt(req.message):
        log.warning("[CHAT] → BLOCKED prompt injection: %r", req.message[:120])
        return ChatResponse(answer="Cô chỉ có thể giúp con học Toán và tra từ Tày/Nùng thôi nhé! 😊", source="safety")

    if is_harmful_content(req.message):
        log.info("[CHAT] → BLOCKED harmful content")
        return ChatResponse(answer="Câu hỏi không phù hợp. Con hãy hỏi về bài học nhé!", source="safety")

    if not is_meaningful_question(req.message):
        log.info("[CHAT] → BLOCKED by is_meaningful_question")
        return ChatResponse(
            answer="Cô chưa hiểu câu hỏi này. Con hãy hỏi về bài Toán hoặc môn học nhé!",
            source="safety",
        )

    # 2. Intent detection → Rule Engine
    intent = detect(req.message)
    if intent:
        log.info("[CHAT] intent=%s  params=%s", intent.rule_fn, intent.params)
        math_result = solve(req.message)
        if math_result and math_result.ok:
            log.info("[CHAT] → rule_engine  answer=%r", math_result.answer)
            return ChatResponse(
                answer=math_result.formula,
                steps=math_result.steps,
                source="rule_engine",
                intent=intent.rule_fn,
            )
        log.warning(
            "[CHAT] Rule Engine failed: %s",
            math_result.error if math_result else "no result",
        )
    else:
        log.info("[CHAT] intent=None → RAG")

    # 3. Vector search
    result = await search(req.message, grade=req.grade)
    # if result and result["score"] >= SCORE_THRESHOLD:
    #     log.info("[CHAT] → rerank score=%.4f  title=%r", result["score"], result.get("title"))
    #     return ChatResponse(
    #         answer=result["content"],
    #         source="vector",
    #         score=result["score"],
    #         grade=result.get("grade"),
    #     )

    # 4. Gemini fallback
    context = result["context"] if result else ""
    log.info(
        "[CHAT] → llm  has_context=%s  rerank_score=%s context=%r",
        bool(context),
        f"{result['top_rerank_score']:.4f}" if result else "N/A",
        context[:100],
    )
    try:
        answer = await ask_gemini(
            prompt=req.message,
            context=context,
            grade=req.grade,
            language=req.language,
            role=req.mode,
        )
        return ChatResponse(answer=answer, source="llm")
    except HTTPException:
        raise
    except Exception as e:
        log.error("[CHAT] Unexpected error: %s", e)
        raise HTTPException(status_code=500, detail="INTERNAL_ERROR")
