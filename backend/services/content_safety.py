import re

# Whitelist: chỉ cho phép các chủ đề giáo dục
ALLOWED_TOPICS = [
    "toán", "tính", "cộng", "trừ", "nhân", "chia", "số", "hình",
    "tiếng việt", "đọc", "viết", "từ", "câu", "đoạn",
    "khoa học", "tự nhiên", "cây", "con vật", "thời tiết",
    "lịch sử", "địa lý", "bài tập", "giải", "học",
]

BLOCKED_PATTERNS = [
    r"\b(hack|cheat|bypass|jailbreak)\b",
    r"(bạo lực|giết|đánh nhau|vũ khí)",
    r"(phim|ảnh)\s*(18\+|người lớn|khiêu dâm)",
    r"(thuốc|ma túy|chất cấm)",
]

def is_safe(text: str) -> bool:
    """Kiểm tra nội dung có phù hợp với trẻ em không."""
    text_lower = text.lower()

    # Chặn các pattern nguy hiểm
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, text_lower):
            return False

    return True
