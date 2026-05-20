import os
import redis.asyncio as aioredis
import hashlib
import google.generativeai as genai

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
CACHE_TTL  = int(os.getenv("REDIS_CACHE_TTL", 86400))

_redis = None

async def get_redis():
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    return _redis

def _cache_key(prompt: str) -> str:
    return "gemini:" + hashlib.md5(prompt.encode()).hexdigest()

async def ask_gemini(prompt: str, grade: int = 3, language: str = "vi") -> str:
    """
    Gọi Gemini API với server-side cache qua Redis.
    Cùng prompt → trả kết quả cache, không gọi lại API.
    """
    cache_key = _cache_key(f"{prompt}:{grade}:{language}")

    # Kiểm tra Redis cache
    r = await get_redis()
    cached = await r.get(cache_key)
    if cached:
        return cached.decode()

    # Gọi Gemini
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        "gemini-2.0-flash",
        system_instruction=(
            f"Bạn là gia sư thân thiện, kiên nhẫn dành cho học sinh lớp {grade} "
            f"người dân tộc thiểu số. Giải thích đơn giản, dùng ví dụ gần gũi "
            f"với cuộc sống vùng cao. Trả lời bằng tiếng Việt."
        ),
    )
    response = model.generate_content(prompt)
    answer = response.text

    # Lưu vào Redis cache
    await r.setex(cache_key, CACHE_TTL, answer)
    return answer
