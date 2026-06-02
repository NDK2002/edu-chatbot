import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

MOCK_PLAN = {
    "objectives": ["Học sinh thuộc bảng nhân 3"],
    "activities": [{"step": 1, "duration": "5 phút", "description": "Khởi động"}],
    "exercises": ["3 × 4 = ?"],
}

@pytest.mark.asyncio
async def test_generate_lesson_no_auth_returns_plan():
    """No auth header → plan generated but not saved (lesson_id=None)."""
    with patch("backend.routers.teacher.search", new_callable=AsyncMock) as mock_search, \
         patch("backend.routers.teacher.ask_gemini_json", new_callable=AsyncMock) as mock_gemini:
        mock_search.return_value = {"retrieval_status": "no_relevant_context", "context": []}
        mock_gemini.return_value = json.dumps(MOCK_PLAN)

        res = client.post("/teacher/lesson", json={"topic": "Bảng nhân 3", "grade": 3, "subject": "Toán"})

    assert res.status_code == 200
    data = res.json()
    assert data["objectives"] == MOCK_PLAN["objectives"]
    assert data["rag_used"] is False
    assert data["id"] is None


@pytest.mark.asyncio
async def test_generate_lesson_with_rag_context():
    """When Qdrant returns strong context, rag_used=True."""
    with patch("backend.routers.teacher.search", new_callable=AsyncMock) as mock_search, \
         patch("backend.routers.teacher.ask_gemini_json", new_callable=AsyncMock) as mock_gemini:
        mock_search.return_value = {
            "retrieval_status": "strong_context",
            "context": [{"content": "Bảng nhân 3: 3×1=3, 3×2=6..."}],
        }
        mock_gemini.return_value = json.dumps(MOCK_PLAN)

        res = client.post("/teacher/lesson", json={"topic": "Bảng nhân 3", "grade": 3, "subject": "Toán"})

    assert res.status_code == 200
    assert res.json()["rag_used"] is True


def test_list_lessons_requires_auth():
    res = client.get("/teacher/lessons")
    assert res.status_code == 401
