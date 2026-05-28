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

_client = None


def get_supabase():
    """Trả singleton Supabase client, hoặc None nếu chưa cấu hình."""
    global _client
    if _client is not None:
        return _client
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        log.warning("[SUPABASE] SUPABASE_URL / SUPABASE_SECRET_KEY chưa set — DB features tắt")
        return None
    from supabase import create_client
    _client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
    return _client


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
    resp = httpx.get(f"{SUPABASE_URL}/auth/v1/jwks", timeout=10.0)
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
