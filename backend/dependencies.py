from fastapi import Header, HTTPException
from backend.services.supabase_client import verify_jwt


async def get_current_user(
    authorization: str | None = Header(None, alias="Authorization"),
) -> str:
    """FastAPI dependency — yêu cầu xác thực. Raise 401 nếu thiếu hoặc token sai."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai Authorization header")
    token = authorization[7:].strip()
    return await verify_jwt(token)


async def get_optional_user(
    authorization: str | None = Header(None, alias="Authorization"),
) -> str | None:
    """FastAPI dependency — không bắt buộc login. Trả None nếu không có token."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    try:
        return await verify_jwt(token)
    except HTTPException:
        return None
