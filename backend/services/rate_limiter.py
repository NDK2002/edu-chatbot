import os
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", 10))
RATE_LIMIT_PER_DAY = int(os.getenv("RATE_LIMIT_PER_DAY", 50))
RATE_LIMIT_WHITELIST = [
    ip.strip() for ip in os.getenv("RATE_LIMIT_WHITELIST", "127.0.0.1,::1").split(",") if ip.strip()
]
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_USERNAME = os.getenv("REDIS_USERNAME", "")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

_redis = None


@dataclass
class RateLimitResult:
    allowed: bool
    remaining_hour: int
    remaining_day: int
    reset_in_seconds: int
    reason: str | None


async def _get_redis():
    global _redis
    import redis.asyncio as aioredis
    if _redis is None:
        if REDIS_USERNAME and REDIS_PASSWORD:
            _redis = await aioredis.from_url(
                f"redis://{REDIS_USERNAME}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}"
            )
        else:
            _redis = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    return _redis


async def check_rate_limit(ip: str, session_id: str) -> RateLimitResult:
    if not RATE_LIMIT_ENABLED:
        return RateLimitResult(
            allowed=True,
            remaining_hour=RATE_LIMIT_PER_HOUR,
            remaining_day=RATE_LIMIT_PER_DAY,
            reset_in_seconds=0,
            reason=None,
        )

    if ip in RATE_LIMIT_WHITELIST:
        return RateLimitResult(
            allowed=True,
            remaining_hour=RATE_LIMIT_PER_HOUR,
            remaining_day=RATE_LIMIT_PER_DAY,
            reset_in_seconds=0,
            reason=None,
        )

    now = datetime.now(timezone.utc)
    hour_key = f"rate:{ip}:{session_id}:hour:{now.strftime('%Y-%m-%d-%H')}"
    day_key = f"rate:{ip}:{session_id}:day:{now.strftime('%Y-%m-%d')}"

    try:
        r = await _get_redis()
        pipe = r.pipeline()
        pipe.incr(hour_key)
        pipe.incr(day_key)
        results = await pipe.execute()

        hour_count = int(results[0])
        day_count = int(results[1])

        # Only set TTL on first increment to avoid resetting the window
        if hour_count == 1:
            await r.expire(hour_key, 3600)
        if day_count == 1:
            await r.expire(day_key, 86400)

        hour_ttl = await r.ttl(hour_key)
        day_ttl = await r.ttl(day_key)

        # Fix TTL if missing (e.g. key existed without expiry before this change)
        if hour_ttl < 0:
            await r.expire(hour_key, 3600)
            hour_ttl = 3600
        if day_ttl < 0:
            await r.expire(day_key, 86400)
            day_ttl = 86400

        remaining_hour = max(0, RATE_LIMIT_PER_HOUR - hour_count)
        remaining_day = max(0, RATE_LIMIT_PER_DAY - day_count)

        if hour_count > RATE_LIMIT_PER_HOUR:
            return RateLimitResult(
                allowed=False,
                remaining_hour=0,
                remaining_day=remaining_day,
                reset_in_seconds=hour_ttl,
                reason="hourly_limit",
            )

        if day_count > RATE_LIMIT_PER_DAY:
            return RateLimitResult(
                allowed=False,
                remaining_hour=remaining_hour,
                remaining_day=0,
                reset_in_seconds=day_ttl,
                reason="daily_limit",
            )

        return RateLimitResult(
            allowed=True,
            remaining_hour=remaining_hour,
            remaining_day=remaining_day,
            reset_in_seconds=hour_ttl,
            reason=None,
        )

    except Exception as e:
        log.warning("[RATE_LIMIT] Redis error, failing open: %s", e)
        return RateLimitResult(
            allowed=True,
            remaining_hour=RATE_LIMIT_PER_HOUR,
            remaining_day=RATE_LIMIT_PER_DAY,
            reset_in_seconds=0,
            reason=None,
        )
