"""
Supabase client singleton + auth/DB helpers for FastAPI backend.

- JWT verification: JWKS endpoint (RS256/ES256) — cơ chế JWT Signing Keys mới của Supabase
  JWKS được cache 1 giờ, chỉ fetch lại khi hết TTL.
- DB calls: sync supabase-py wrapped trong asyncio.to_thread()
- Graceful degradation: nếu env vars chưa set, DB features tắt nhưng app vẫn chạy
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from jose import JWTError, jwt

load_dotenv()

log = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")

_client = None


def get_supabase():
    """Trả singleton Supabase client, hoặc None nếu chưa cấu hình."""
    global _client
    if _client is not None:
        return _client
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        log.warning(
            "[SUPABASE] env thiếu — URL=%s KEY=%s",
            bool(SUPABASE_URL), bool(SUPABASE_SECRET_KEY),
        )
        return None
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
        log.info("[SUPABASE] client khởi tạo thành công")
        return _client
    except Exception as exc:
        log.error("[SUPABASE] create_client thất bại: %s", exc)
        return None


# ---------------------------------------------------------------------------
# JWT verification — JWKS (JWT Signing Keys, cơ chế mới của Supabase)
# ---------------------------------------------------------------------------

_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 3600.0  # cache 1 giờ


def _fetch_jwks() -> dict:
    """Lấy JWKS từ Supabase Auth, có cache 1 giờ (sync, gọi qua asyncio.to_thread)."""
    global _jwks_cache, _jwks_fetched_at
    now = time.monotonic()
    if _jwks_cache is not None and now - _jwks_fetched_at < _JWKS_TTL:
        return _jwks_cache
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL chưa set")
    api_key = SUPABASE_PUBLISHABLE_KEY or SUPABASE_SECRET_KEY
    resp = httpx.get(
        f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json",
        headers={"apikey": api_key} if api_key else {},
        timeout=10.0,
    )
    resp.raise_for_status()
    _jwks_cache = resp.json()
    _jwks_fetched_at = now
    log.info("[SUPABASE] JWKS refreshed")
    return _jwks_cache


async def verify_jwt(token: str) -> str:
    """
    Verify Supabase JWT bằng JWKS endpoint (RS256 / ES256).
    Trả user_id (uuid string) hoặc raise HTTP 401.
    """
    if not SUPABASE_URL:
        raise HTTPException(status_code=401, detail="SUPABASE_URL chưa được cấu hình")
    try:
        jwks = await asyncio.to_thread(_fetch_jwks)
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
        )
        return payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Token không hợp lệ hoặc đã hết hạn")
    except Exception as exc:
        log.warning("[SUPABASE] JWT verify error: %s", exc)
        raise HTTPException(status_code=401, detail="Không thể xác thực token")


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _get_or_create_session_sync(user_id: str, mode: str) -> str:
    sb = get_supabase()
    if sb is None:
        raise RuntimeError("Supabase chưa cấu hình")

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    resp = (
        sb.table("chat_sessions")
        .select("id")
        .eq("user_id", user_id)
        .eq("mode", mode)
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if resp.data:
        return resp.data[0]["id"]

    new = sb.table("chat_sessions").insert({"user_id": user_id, "mode": mode}).execute()
    return new.data[0]["id"]


async def get_or_create_session(user_id: str, mode: str) -> str:
    return await asyncio.to_thread(_get_or_create_session_sync, user_id, mode)


# ---------------------------------------------------------------------------
# Message persistence
# ---------------------------------------------------------------------------

def _save_messages_sync(
    session_id: str,
    user_content: str,
    assistant_content: str,
    query_type: str,
    source: str,
) -> None:
    sb = get_supabase()
    if sb is None:
        return
    sb.table("chat_messages").insert([
        {
            "session_id": session_id,
            "role": "user",
            "content": user_content,
            "query_type": query_type,
            "source": source,
        },
        {
            "session_id": session_id,
            "role": "assistant",
            "content": assistant_content,
            "query_type": query_type,
            "source": source,
        },
    ]).execute()


async def save_messages(
    session_id: str,
    user_content: str,
    assistant_content: str,
    query_type: str,
    source: str,
) -> None:
    await asyncio.to_thread(
        _save_messages_sync,
        session_id,
        user_content,
        assistant_content,
        query_type,
        source,
    )


# ---------------------------------------------------------------------------
# Conversation helpers (new conversation management system)
# ---------------------------------------------------------------------------

def _list_conversations_sync(user_id: str) -> list[dict]:
    sb = get_supabase()
    if sb is None:
        return []
    resp = (
        sb.table("conversations")
        .select("id, title, mode, is_compacted, message_count, last_message_at, created_at")
        .eq("user_id", user_id)
        .order("last_message_at", desc=True)
        .execute()
    )
    return resp.data or []


async def list_conversations(user_id: str) -> list[dict]:
    return await asyncio.to_thread(_list_conversations_sync, user_id)


def _create_conversation_sync(user_id: str, mode: str) -> dict:
    sb = get_supabase()
    if sb is None:
        raise RuntimeError("Supabase chưa cấu hình")
    resp = (
        sb.table("conversations")
        .insert({"user_id": user_id, "mode": mode})
        .execute()
    )
    return resp.data[0]


async def create_conversation(user_id: str, mode: str) -> dict:
    return await asyncio.to_thread(_create_conversation_sync, user_id, mode)


def _delete_conversation_sync(conv_id: str, user_id: str) -> None:
    sb = get_supabase()
    if sb is None:
        return
    sb.table("conversations").delete().eq("id", conv_id).eq("user_id", user_id).execute()


async def delete_conversation(conv_id: str, user_id: str) -> None:
    await asyncio.to_thread(_delete_conversation_sync, conv_id, user_id)


def _get_conversation_messages_sync(conv_id: str, user_id: str) -> dict | None:
    sb = get_supabase()
    if sb is None:
        return {"compact_summary": None, "messages": []}
    conv_resp = (
        sb.table("conversations")
        .select("id, compact_summary")
        .eq("id", conv_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not conv_resp.data:
        return None
    conv = conv_resp.data[0]
    msgs_resp = (
        sb.table("messages")
        .select("id, role, content, query_type, source, steps, is_compacted, created_at")
        .eq("conversation_id", conv_id)
        .eq("is_compacted", False)
        .order("created_at", desc=False)
        .execute()
    )
    return {
        "compact_summary": conv.get("compact_summary"),
        "messages": msgs_resp.data or [],
    }


async def get_conversation_messages(conv_id: str, user_id: str) -> dict | None:
    return await asyncio.to_thread(_get_conversation_messages_sync, conv_id, user_id)


def _update_conversation_title_sync(conv_id: str, user_id: str, title: str) -> dict:
    sb = get_supabase()
    if sb is None:
        raise RuntimeError("Supabase chưa cấu hình")
    resp = (
        sb.table("conversations")
        .update({"title": title})
        .eq("id", conv_id)
        .eq("user_id", user_id)
        .execute()
    )
    return resp.data[0] if resp.data else {}


async def update_conversation_title(conv_id: str, user_id: str, title: str) -> dict:
    return await asyncio.to_thread(_update_conversation_title_sync, conv_id, user_id, title)


def _get_recent_history_sync(conv_id: str, limit: int = 20) -> dict:
    """Get compact_summary + recent uncompacted messages for Gemini context."""
    sb = get_supabase()
    if sb is None:
        return {"compact_summary": None, "messages": [], "message_count": 0}
    conv_resp = (
        sb.table("conversations")
        .select("compact_summary, message_count")
        .eq("id", conv_id)
        .execute()
    )
    if not conv_resp.data:
        return {"compact_summary": None, "messages": [], "message_count": 0}
    conv = conv_resp.data[0]
    msgs_resp = (
        sb.table("messages")
        .select("role, content")
        .eq("conversation_id", conv_id)
        .eq("is_compacted", False)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    messages = list(reversed(msgs_resp.data or []))
    return {
        "compact_summary": conv.get("compact_summary"),
        "messages": messages,
        "message_count": conv.get("message_count", 0),
    }


async def get_recent_history(conv_id: str, limit: int = 20) -> dict:
    return await asyncio.to_thread(_get_recent_history_sync, conv_id, limit)


def _save_conv_messages_sync(
    conv_id: str,
    user_content: str,
    assistant_content: str,
    query_type: str,
    source: str,
    auto_title: str | None,
    new_count: int,
    steps: list[str] | None = None,
) -> None:
    sb = get_supabase()
    if sb is None:
        return
    assistant_row: dict = {
        "conversation_id": conv_id,
        "role": "assistant",
        "content": assistant_content,
        "query_type": query_type,
        "source": source,
    }
    if steps:
        assistant_row["steps"] = steps
    sb.table("messages").insert([
        {
            "conversation_id": conv_id,
            "role": "user",
            "content": user_content,
            "query_type": query_type,
            "source": source,
        },
        assistant_row,
    ]).execute()
    update_data: dict = {
        "message_count": new_count,
        "last_message_at": datetime.now(timezone.utc).isoformat(),
    }
    if auto_title:
        update_data["title"] = auto_title
    sb.table("conversations").update(update_data).eq("id", conv_id).execute()


async def save_conv_messages(
    conv_id: str,
    user_content: str,
    assistant_content: str,
    query_type: str,
    source: str,
    auto_title: str | None = None,
    current_count: int = 0,
    steps: list[str] | None = None,
) -> None:
    await asyncio.to_thread(
        _save_conv_messages_sync,
        conv_id,
        user_content,
        assistant_content,
        query_type,
        source,
        auto_title,
        current_count + 2,
        steps,
    )


def _count_uncompacted_sync(conv_id: str) -> int:
    sb = get_supabase()
    if sb is None:
        return 0
    resp = (
        sb.table("messages")
        .select("id", count="exact")
        .eq("conversation_id", conv_id)
        .eq("is_compacted", False)
        .execute()
    )
    return resp.count or 0


async def count_uncompacted(conv_id: str) -> int:
    return await asyncio.to_thread(_count_uncompacted_sync, conv_id)


def _get_all_uncompacted_sync(conv_id: str) -> list[dict]:
    sb = get_supabase()
    if sb is None:
        return []
    resp = (
        sb.table("messages")
        .select("id, role, content, created_at")
        .eq("conversation_id", conv_id)
        .eq("is_compacted", False)
        .order("created_at", desc=False)
        .execute()
    )
    return resp.data or []


async def get_all_uncompacted(conv_id: str) -> list[dict]:
    return await asyncio.to_thread(_get_all_uncompacted_sync, conv_id)


def _mark_messages_compacted_sync(message_ids: list[str]) -> None:
    sb = get_supabase()
    if sb is None or not message_ids:
        return
    sb.table("messages").update({"is_compacted": True}).in_("id", message_ids).execute()


async def mark_messages_compacted(message_ids: list[str]) -> None:
    await asyncio.to_thread(_mark_messages_compacted_sync, message_ids)


def _set_compact_summary_sync(conv_id: str, summary: str) -> None:
    sb = get_supabase()
    if sb is None:
        return
    sb.table("conversations").update({
        "compact_summary": summary,
        "is_compacted": True,
    }).eq("id", conv_id).execute()


async def set_compact_summary(conv_id: str, summary: str) -> None:
    await asyncio.to_thread(_set_compact_summary_sync, conv_id, summary)
