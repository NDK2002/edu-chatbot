import math
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from backend.services.rate_limiter import check_rate_limit

_RATE_LIMITED_PATHS = {"/chat", "/chat/", "/v2/chat", "/v2/chat/"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method != "POST" or request.url.path not in _RATE_LIMITED_PATHS:
            return await call_next(request)

        # Prefer X-Forwarded-For when behind a proxy/load-balancer
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        session_id = request.cookies.get("edu_session")
        is_new_session = session_id is None
        if is_new_session:
            session_id = str(uuid.uuid4())

        result = await check_rate_limit(ip, session_id)

        if not result.allowed:
            if result.reset_in_seconds < 60:
                time_str = f"{result.reset_in_seconds} giây"
            else:
                time_str = f"{math.ceil(result.reset_in_seconds / 60)} phút"

            body = {
                "error": "rate_limit_exceeded",
                "reason": result.reason,
                "remaining_hour": result.remaining_hour,
                "remaining_day": result.remaining_day,
                "reset_in_seconds": result.reset_in_seconds,
                "message": f"Bạn đã hỏi quá nhiều. Vui lòng thử lại sau {time_str}.",
            }
            response = JSONResponse(status_code=429, content=body)
            if is_new_session:
                response.set_cookie(
                    "edu_session", session_id,
                    httponly=True, samesite="lax", max_age=86400 * 30,
                )
            return response

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining-Hour"] = str(result.remaining_hour)
        response.headers["X-RateLimit-Remaining-Day"] = str(result.remaining_day)
        response.headers["X-RateLimit-Reset"] = str(result.reset_in_seconds)
        if is_new_session:
            response.set_cookie(
                "edu_session", session_id,
                httponly=True, samesite="lax", max_age=86400 * 30,
            )
        return response
