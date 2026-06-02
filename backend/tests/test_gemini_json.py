import pytest
import json
from unittest.mock import MagicMock, patch
from backend.services.gemini import ask_gemini_json


@pytest.mark.asyncio
async def test_ask_gemini_json_returns_string():
    mock_response = MagicMock()
    mock_response.text = '{"objectives": ["test"], "activities": [], "exercises": []}'

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("backend.services.gemini._get_client", return_value=mock_client):
        result = await ask_gemini_json("soạn giáo án bảng nhân 3", role="teacher")

    assert isinstance(result, str)
    parsed = json.loads(result)
    assert "objectives" in parsed
