import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from backend.services.gemini import ask_gemini_json
from backend.services.supabase_client import get_supabase, verify_jwt
from backend.services.vector_search import search

log = logging.getLogger(__name__)
router = APIRouter()


class LessonRequest(BaseModel):
    topic: str
    grade: int = 3
    subject: str = "Toán"


class LessonResponse(BaseModel):
    id: Optional[str] = None
    topic: str
    grade: int
    subject: str
    objectives: list[str]
    activities: list[dict]
    exercises: list[str]
    rag_used: bool


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _save_lesson_sync(
    user_id: str,
    topic: str,
    grade: int,
    subject: str,
    objectives: list,
    activities: list,
    exercises: list,
    rag_used: bool,
) -> str:
    sb = get_supabase()
    if sb is None:
        raise RuntimeError("Supabase not configured")
    resp = (
        sb.table("lesson_plans")
        .insert({
            "user_id": user_id,
            "topic": topic,
            "grade": grade,
            "subject": subject,
            "objectives": objectives,
            "activities": activities,
            "exercises": exercises,
            "rag_used": rag_used,
        })
        .execute()
    )
    return resp.data[0]["id"]


def _update_lesson_sync(
    user_id: str,
    lesson_id: str,
    objectives: list,
    activities: list,
    exercises: list,
) -> Optional[dict]:
    sb = get_supabase()
    if sb is None:
        raise RuntimeError("Supabase not configured")
    resp = (
        sb.table("lesson_plans")
        .update({"objectives": objectives, "activities": activities, "exercises": exercises})
        .eq("id", lesson_id)
        .eq("user_id", user_id)
        .execute()
    )
    return resp.data[0] if resp.data else None


def _list_lessons_sync(
    user_id: str,
    grade: Optional[int],
    subject: Optional[str],
) -> list[dict]:
    sb = get_supabase()
    if sb is None:
        return []
    query = (
        sb.table("lesson_plans")
        .select("id, topic, grade, subject, objectives, activities, exercises, rag_used, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
    )
    if grade is not None:
        query = query.eq("grade", grade)
    if subject:
        query = query.eq("subject", subject)
    return query.execute().data or []


@router.post("/lesson", response_model=LessonResponse)
async def generate_lesson(
    req: LessonRequest,
    authorization: Optional[str] = Header(None),
):
    # 1. RAG search (grade=0 → no grade filter, search all lớp 1–5)
    rag_context = ""
    rag_used = False
    try:
        rag_result = await search(req.topic, grade=0, top_k=40)
        if rag_result and rag_result.get("retrieval_status") in ("strong_context", "medium_context"):
            contexts = rag_result.get("context", [])
            if contexts:
                rag_context = "\n\n".join(c["content"] for c in contexts[:3])
                rag_used = True
    except Exception as e:
        log.warning("[TEACHER] RAG search failed, proceeding without context: %s", e)

    # 2. Build prompt
    json_schema = (
        '{"objectives": ["chuỗi mục tiêu"], '
        '"activities": [{"step": 1, "duration": "5 phút", "description": "mô tả"}], '
        '"exercises": ["bài tập"]}'
    )
    base_instruction = (
        f"Soạn giáo án môn {req.subject} lớp {req.grade}, chủ đề: {req.topic}. "
        f"Dùng ví dụ gần gũi với học sinh Tày/Nùng vùng cao (núi rừng, nương rẫy, lễ hội dân tộc). "
        f"Ví dụ minh họa phải cân bằng giới tính: dùng cả tên bạn nam lẫn bạn nữ, "
        f"không gán nghề nghiệp hay vai trò theo giới tính (ví dụ không chỉ 'bố đi làm, mẹ nấu cơm'). "
        f"Chuẩn kiến thức theo GDPT 2018. "
        f"Trả về JSON đúng format: {json_schema}"
    )
    if rag_context:
        prompt = (
            f"Dưới đây là nội dung từ SGK Cánh Diều lớp {req.grade}:\n{rag_context}\n\n"
            f"Dựa trên nội dung trên, {base_instruction}"
        )
    else:
        prompt = base_instruction

    # 3. Gemini JSON
    json_text = await ask_gemini_json(prompt, role="teacher")
    json_text = _strip_json_fence(json_text)
    try:
        plan = json.loads(json_text)
    except json.JSONDecodeError:
        log.error("[TEACHER] Invalid JSON from Gemini: %.200s", json_text)
        raise HTTPException(status_code=500, detail="AI trả về định dạng không hợp lệ")

    objectives = plan.get("objectives", [])
    activities = plan.get("activities", [])
    exercises = plan.get("exercises", [])

    # 4. Save to Supabase (best-effort — don't fail generation if save fails)
    lesson_id = None
    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
        try:
            user_id = await verify_jwt(token)
            lesson_id = await asyncio.to_thread(
                _save_lesson_sync, user_id, req.topic, req.grade, req.subject,
                objectives, activities, exercises, rag_used,
            )
        except Exception as e:
            log.warning("[TEACHER] Save lesson failed: %s", e)

    return LessonResponse(
        id=lesson_id,
        topic=req.topic,
        grade=req.grade,
        subject=req.subject,
        objectives=objectives,
        activities=activities,
        exercises=exercises,
        rag_used=rag_used,
    )


class LessonUpdateRequest(BaseModel):
    objectives: list[str]
    activities: list[dict]
    exercises: list[str]


@router.put("/lesson/{lesson_id}", response_model=LessonResponse)
async def update_lesson(
    lesson_id: str,
    req: LessonUpdateRequest,
    authorization: Optional[str] = Header(None),
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    token = authorization.removeprefix("Bearer ").strip()
    user_id = await verify_jwt(token)
    row = await asyncio.to_thread(
        _update_lesson_sync, user_id, lesson_id, req.objectives, req.activities, req.exercises
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Giáo án không tìm thấy")
    return LessonResponse(
        id=row["id"],
        topic=row["topic"],
        grade=row["grade"],
        subject=row["subject"],
        objectives=row["objectives"],
        activities=row["activities"],
        exercises=row["exercises"],
        rag_used=row.get("rag_used", False),
    )


@router.get("/lessons")
async def list_lessons(
    grade: Optional[int] = Query(None),
    subject: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    token = authorization.removeprefix("Bearer ").strip()
    user_id = await verify_jwt(token)
    lessons = await asyncio.to_thread(_list_lessons_sync, user_id, grade, subject)
    return {"lessons": lessons}
