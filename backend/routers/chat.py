from fastapi import APIRouter
from pydantic import BaseModel
from backend.services.content_safety import is_safe
from backend.services.vector_search import search
from backend.services.gemini import ask_gemini

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    grade: int = 3
    language: str = "vi"   # "vi" | "hmong"

class ChatResponse(BaseModel):
    answer: str
    source: str            # "vector" | "llm"
    score: float | None = None

@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # 1. Kiểm duyệt nội dung
    if not is_safe(req.message):
        return ChatResponse(answer="Câu hỏi không phù hợp.", source="safety")

    # 2. Vector search trước
    result = await search(req.message, grade=req.grade)
    if result and result["score"] >= 0.82:
        return ChatResponse(
            answer=result["content"],
            source="vector",
            score=result["score"]
        )

    # 3. Fallback: gọi Gemini
    answer = await ask_gemini(req.message, grade=req.grade, language=req.language)
    return ChatResponse(answer=answer, source="llm")
