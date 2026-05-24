import os
from fastapi import APIRouter
from pydantic import BaseModel
from backend.services.content_safety import is_safe
from backend.services.vector_search import search
from backend.services.gemini import ask_gemini
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    grade: int = 0          # 0 = no grade filter (search all grades 1–5)
    language: str = "vi"    # "vi" | "tay_nung"

class ChatResponse(BaseModel):
    answer: str
    source: str            # "vector" | "llm"
    score: float | None = None

@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # 1. Validate input
    if not is_safe(req.message):
        return ChatResponse(answer="Câu hỏi không phù hợp.", source="safety")

    # 2. Vector search first
    result = await search(req.message, grade=req.grade)
    if result and result["score"] >= float(os.getenv("VECTOR_SCORE_THRESHOLD", 0.5)):
        return ChatResponse(
            answer=result["content"],
            source="vector",
            score=result["score"]
        )

    context = result["content"] if result else ""
    answer = await ask_gemini(
        prompt=req.message, 
        context=context, 
        grade=req.grade, 
        language=req.language
    )
    return ChatResponse(answer=answer, source="llm")
