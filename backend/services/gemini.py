import os
import logging
import redis.asyncio as aioredis
import hashlib
from typing import AsyncGenerator
from google import genai
from google.genai import types
from dotenv import load_dotenv
from google.genai.errors import ServerError
from fastapi import HTTPException
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception



load_dotenv()
log = logging.getLogger(__name__)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_USERNAME = os.getenv("REDIS_USERNAME", "")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL", 86400))

_redis = None
_client = None

FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


BASE_PROMPT = """
Bạn là trợ lý học tập cho học sinh tiểu học vùng cao dân tộc Tày/Nùng tại Việt Nam.

## Vai trò
- Hỗ trợ học tập theo chương trình SGK tiểu học
- Giải thích bằng tiếng Việt đơn giản, rõ ràng
- Kèm từ khóa song ngữ Việt–Tày/Nùng khi có trong từ điển

## Nguyên tắc trả lời
- Luôn trả lời bằng tiếng Việt
- Không tự bịa từ Tày/Nùng — chỉ dùng từ có trong từ điển được cung cấp
- Nếu không có từ Tày/Nùng, ghi rõ: "Chưa có từ Tày/Nùng đã kiểm chứng cho từ này"
- Không bịa đáp số, không tự tính toán — kết quả Toán do hệ thống tính sẵn
- Nếu không chắc, nói thẳng: "Mình không chắc, em nên hỏi thầy cô"

## Format trả lời
Với bài Toán:
1. Giải thích từ khó trong đề (nếu có)
2. Nêu công thức hoặc kiến thức cần dùng
3. Lời giải từng bước rõ ràng

Với câu hỏi từ điển:
1. Trả lời trực tiếp
2. Ghi rõ biến thể vùng nếu có nhiều cách nói
3. Bảng "Từ cần nhớ" Việt–Tày/Nùng (nếu có từ trong từ điển)

## Giới hạn
- Chỉ trả lời về các môn học tiểu học và từ điển Tày/Nùng
- Từ chối lịch sự các chủ đề không liên quan đến học tập
- Không có thông tin cá nhân của học sinh
"""

STUDENT_BLOCK = """
## Chế độ: Học sinh

Đối tượng: học sinh tiểu học 6–15 tuổi, có thể chưa thông thạo tiếng Việt.

- Dùng câu ngắn, từ ngữ đơn giản
- Chia nhỏ từng bước, không giải thích dài
- Hỏi ngược lại trước khi đưa đáp án: "Em thử nghĩ xem bước đầu tiên là gì?"
- Động viên khi học sinh trả lời đúng
- Xưng "mình", gọi học sinh là "em"
"""

TEACHER_BLOCK = """
## Chế độ: Giáo viên

Đối tượng: giáo viên tiểu học vùng cao.

- Dùng ngôn ngữ chuyên nghiệp
- Kèm chuẩn kiến thức và mục tiêu bài học theo GDPT 2018
- Hỗ trợ soạn giáo án phù hợp văn hóa địa phương Tày/Nùng
- Có thể đề xuất ví dụ thực tế gần gũi với học sinh vùng cao
(ruộng bậc thang, nương rẫy, chợ phiên, lễ hội...)
- Xưng "tôi", gọi giáo viên là "thầy/cô"
"""

system_prompt = BASE_PROMPT + STUDENT_BLOCK

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


async def _get_redis():
    global _redis
    if _redis is None:
        if REDIS_USERNAME and REDIS_PASSWORD:
            _redis = await aioredis.from_url(f"redis://{REDIS_USERNAME}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}")
        else:
            _redis = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    return _redis


def _cache_key(prompt: str) -> str:
    return "gemini:" + hashlib.md5(prompt.encode()).hexdigest()

def get_system_prompt(role: str = "student") -> str:
    if role == "teacher":
        return BASE_PROMPT + TEACHER_BLOCK
    return BASE_PROMPT + STUDENT_BLOCK

def is_503(e):
    return isinstance(e, ServerError) and e.code == 503

@retry(
    retry=retry_if_exception(is_503),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    stop=stop_after_attempt(3),
    reraise=True,
)

async def ask_gemini(prompt: str, context: str = "", grade: int = 3, language: str = "vi", role: str = "student") -> str:
    """
    Gọi Gemini API với server-side cache qua Redis.
    Cùng prompt → trả kết quả cache, không gọi lại API.
    """
    cache_key = _cache_key(f"{prompt}:{context}:{grade}:{language}:{role}")

    r = await _get_redis()
    cached = await r.get(cache_key)
    if cached:
        log.info("[GEMINI] cache hit for key=%s", cache_key)
        return cached.decode()

    # full_prompt with RAG context
    if context:
        full_prompt = f"Dựa vào tài liệu sau:\n{context}\n\nHãy trả lời câu hỏi: {prompt}"
    else:     
        full_prompt = prompt

    if grade:
        full_prompt = f"{full_prompt}\n\nLưu ý: Học sinh đang học lớp {grade}."

    client = _get_client()
    
    for model in FALLBACK_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=get_system_prompt(role),
                    max_output_tokens=2048,
                    temperature=0.2,
                ),
            )
            if model != FALLBACK_MODELS[0]:
                log.warning("[GEMINI] Fallback to model %s due to previous failure", model)
            
            answer = response.text
            await r.setex(cache_key, CACHE_TTL, answer)
            return answer

        except ServerError as e:
            if e.code == 503:
                log.warning("[GEMINI] Model %s is unavailable (503). Retrying with next model...", model)
                continue
            raise
    raise HTTPException(status_code=503, detail="AI_UNAVAILABLE")


async def stream_gemini(
    prompt: str,
    context: str = "",
    grade: int = 3,
    language: str = "vi",
    role: str = "student",
) -> AsyncGenerator[str, None]:
    """Stream response từ Gemini. Cache hit → yield single chunk từ Redis; miss → stream + lưu cache."""
    cache_key = _cache_key(f"{prompt}:{context}:{grade}:{language}:{role}")

    try:
        r = await _get_redis()
        cached = await r.get(cache_key)
        if cached:
            log.info("[GEMINI] stream cache hit  key=%s", cache_key[:40])
            yield cached.decode("utf-8")
            return
    except Exception as e:
        log.warning("[GEMINI] Redis unavailable, skipping cache: %s", e)
        r = None

    if context:
        full_prompt = f"Dựa vào tài liệu sau:\n{context}\n\nHãy trả lời câu hỏi: {prompt}"
    else:
        full_prompt = prompt

    if grade:
        full_prompt = f"{full_prompt}\n\nLưu ý: Học sinh đang học lớp {grade}."

    client = _get_client()
    log.info("[GEMINI] stream cache miss → Gemini  key=%s", cache_key[:40])

    for model in FALLBACK_MODELS:
        try:
            full_response = ""
            stream = await client.aio.models.generate_content_stream(
                model=model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=get_system_prompt(role),
                    max_output_tokens=2048,
                    temperature=0.2,
                ),
            )
            async for chunk in stream:
                if chunk.text:
                    full_response += chunk.text
                    yield chunk.text

            if full_response and r is not None:
                try:
                    await r.setex(cache_key, CACHE_TTL, full_response.encode("utf-8"))
                    log.info("[GEMINI] stream cached  key=%s  len=%d", cache_key[:40], len(full_response))
                except Exception as e:
                    log.warning("[GEMINI] Failed to write stream cache: %s", e)
            return
        except ServerError as e:
            if e.code == 503:
                log.warning("[GEMINI] Model %s unavailable (503), trying next...", model)
                continue
            raise
    raise HTTPException(status_code=503, detail="AI_UNAVAILABLE")
