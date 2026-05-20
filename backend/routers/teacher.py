from fastapi import APIRouter
from pydantic import BaseModel
from backend.services.gemini import ask_gemini

router = APIRouter()

class LessonRequest(BaseModel):
    topic: str           # vd: "Bảng nhân 3"
    grade: int = 3
    subject: str = "toan"

class LessonResponse(BaseModel):
    lesson_plan: str

@router.post("/lesson", response_model=LessonResponse)
async def generate_lesson(req: LessonRequest):
    prompt = (
        f"Soạn giáo án môn {req.subject} lớp {req.grade}, chủ đề: {req.topic}. "
        f"Dùng ví dụ gần gũi với trẻ em vùng cao (núi rừng, nương rẫy, lễ hội H'Mông). "
        f"Trình bày: mục tiêu, hoạt động, bài tập."
    )
    lesson = await ask_gemini(prompt, grade=req.grade)
    return LessonResponse(lesson_plan=lesson)
