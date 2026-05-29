"""
Router /conversations — quản lý conversations (tạo, xóa, lấy messages, đổi title).
Tất cả endpoints đều yêu cầu Bearer token.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.dependencies import get_current_user
from backend.services.supabase_client import (
    create_conversation,
    delete_conversation,
    get_conversation_messages,
    list_conversations,
    update_conversation_title,
)

router = APIRouter()
log = logging.getLogger(__name__)


def _require_supabase():
    from backend.services.supabase_client import get_supabase
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Dịch vụ lưu trữ chưa sẵn sàng")
    return sb


# ---------------------------------------------------------------------------
# List conversations
# ---------------------------------------------------------------------------

@router.get("")
async def get_conversations(user_id: str = Depends(get_current_user)):
    """Lấy danh sách conversations của user, sort by last_message_at desc."""
    _require_supabase()
    return await list_conversations(user_id)


# ---------------------------------------------------------------------------
# Create conversation
# ---------------------------------------------------------------------------

class CreateConvRequest(BaseModel):
    mode: str = "student"


@router.post("", status_code=201)
async def new_conversation(
    body: CreateConvRequest,
    user_id: str = Depends(get_current_user),
):
    """Tạo conversation mới, trả về id + title mặc định."""
    _require_supabase()
    if body.mode not in ("student", "teacher"):
        raise HTTPException(status_code=400, detail="mode phải là 'student' hoặc 'teacher'")
    conv = await create_conversation(user_id, body.mode)
    return conv


# ---------------------------------------------------------------------------
# Delete conversation
# ---------------------------------------------------------------------------

@router.delete("/{conv_id}", status_code=204)
async def remove_conversation(
    conv_id: str,
    user_id: str = Depends(get_current_user),
):
    """Xóa conversation + toàn bộ messages (cascade)."""
    _require_supabase()
    await delete_conversation(conv_id, user_id)
    return None


# ---------------------------------------------------------------------------
# Get conversation messages
# ---------------------------------------------------------------------------

@router.get("/{conv_id}/messages")
async def get_messages(
    conv_id: str,
    user_id: str = Depends(get_current_user),
):
    """Lấy messages chưa compact + compact_summary nếu có."""
    _require_supabase()
    data = await get_conversation_messages(conv_id, user_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Conversation không tồn tại")
    return data


# ---------------------------------------------------------------------------
# Patch conversation title
# ---------------------------------------------------------------------------

class PatchTitleRequest(BaseModel):
    title: str


@router.patch("/{conv_id}/title")
async def patch_title(
    conv_id: str,
    body: PatchTitleRequest,
    user_id: str = Depends(get_current_user),
):
    """Đổi title của conversation."""
    _require_supabase()
    title = body.title.strip()[:100]
    if not title:
        raise HTTPException(status_code=400, detail="Title không được để trống")
    return await update_conversation_title(conv_id, user_id, title)
