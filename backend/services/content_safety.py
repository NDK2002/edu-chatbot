import re

# Whitelist: only allow educational topics
ALLOWED_TOPICS = [
    "toán",
    "tính",
    "cộng",
    "trừ",
    "nhân",
    "chia",
    "số",
    "hình",
    "tiếng việt",
    "đọc",
    "viết",
    "từ",
    "câu",
    "đoạn",
    "khoa học",
    "tự nhiên",
    "cây",
    "con vật",
    "thời tiết",
    "lịch sử",
    "địa lý",
    "bài tập",
    "giải",
    "học",
]

BLOCKED_PATTERNS = [
    r"\b(hack|cheat|bypass|jailbreak)\b",
    r"(bạo lực|giết|đánh nhau|vũ khí)",
    r"(phim|ảnh)\s*(18\+|người lớn|khiêu dâm)",
    r"(thuốc|ma túy|chất cấm)",
]


def is_safe(text: str) -> bool:
    """Check if content is suitable for children."""
    text_lower = text.lower()

    # Block dangerous patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, text_lower):
            return False

    return True
