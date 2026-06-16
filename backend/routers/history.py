"""
Router /history — từ đã lưu của user đã đăng nhập.
Tất cả endpoints đều yêu cầu Bearer token hợp lệ.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.dependencies import get_current_user
from backend.services.supabase_client import get_supabase

router = APIRouter()
log = logging.getLogger(__name__)


def _require_supabase():
    sb = get_supabase()
    if sb is None:
        raise HTTPException(status_code=503, detail="Dịch vụ lưu trữ chưa sẵn sàng")
    return sb


# ---------------------------------------------------------------------------
# Saved vocab
# ---------------------------------------------------------------------------

class VocabIn(BaseModel):
    vi: str
    tay_variants: list[str] | None = None
    nung_variants: list[str] | None = None


@router.post("/vocab", status_code=201)
async def save_vocab(payload: VocabIn, user_id: str = Depends(get_current_user)):
    """Lưu (hoặc cập nhật) một từ vào danh sách đã lưu."""
    sb = _require_supabase()
    resp = await asyncio.to_thread(
        lambda: sb.table("saved_vocab")
        .upsert(
            {
                "user_id": user_id,
                "vi": payload.vi.strip(),
                "tay_variants": payload.tay_variants or [],
                "nung_variants": payload.nung_variants or [],
                "is_deleted": 0,
            },
            on_conflict="user_id, vi",
        )
        .execute()
    )
    return resp.data[0] if resp.data else {}


@router.get("/vocab")
async def list_vocab(user_id: str = Depends(get_current_user)):
    """Lấy danh sách từ đã lưu của user."""
    sb = _require_supabase()
    resp = await asyncio.to_thread(
        lambda: sb.table("saved_vocab")
        .select("id, vi, tay_variants, nung_variants, saved_at")
        .eq("user_id", user_id)
        .eq("is_deleted", 0)
        .order("saved_at", desc=True)
        .execute()
    )
    return resp.data


class VocabDelete(BaseModel):
    vi: str


@router.delete("/vocab", status_code=204)
async def delete_vocab(payload: VocabDelete, user_id: str = Depends(get_current_user)):
    """Xóa mềm một từ đã lưu (theo vi text)."""
    sb = _require_supabase()
    await asyncio.to_thread(
        lambda: sb.table("saved_vocab")
        .update({"is_deleted": 1})
        .eq("user_id", user_id)
        .eq("vi", payload.vi.strip())
        .execute()
    )
    return None


@router.delete("/vocab/all", status_code=204)
async def delete_all_vocab(user_id: str = Depends(get_current_user)):
    """Xóa mềm tất cả từ đã lưu."""
    sb = _require_supabase()
    await asyncio.to_thread(
        lambda: sb.table("saved_vocab")
        .update({"is_deleted": 1})
        .eq("user_id", user_id)
        .execute()
    )
    return None
