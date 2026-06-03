import re

# ---------------------------------------------------------------------------
# Layer 1 — Harmful content (violence, sexual, drugs, profanity)
# ---------------------------------------------------------------------------

_HARM_PATTERNS = [
    r"(bạo lực|giết|đánh nhau|vũ khí|chém|đâm|nổ|khủng bố|tấn công|xả súng|đánh bom)",
    r"thằng chó|đồ chó|đồ đĩ|đồ con lợn|đồ con chó|đồ con đĩ|đồ con cặc|đồ con lồn",
    r"con chim|con cặc|đụ mẹ|đụ bố|đụ con|đụ vợ|đụ gái|đụ lồn|đụ em|đụ anh|đụ chị",
    r"(sex|sexual|nude|porn|xxx|dâm|địt|lồn|cặc|đụ|đéo|đĩ|gái gọi)",
    r"\b(drug|cocaine|heroin|meth|weed|marijuana|thuốc lắc|ma túy|chất cấm)\b",
    r"\bkill\b|suicide|self[- ]?harm|tự tử|tự sát|tự hại",
    r"(phim|ảnh)\s*(18\+|người lớn|khiêu dâm)",
]

# ---------------------------------------------------------------------------
# Layer 2 — Prompt injection (English variants)
# ---------------------------------------------------------------------------

_INJECTION_EN = [
    r"ignore\s+(previous|all|prior|your|any)\s+instructions?",
    r"(forget|disregard|override)\s+(everything|all|what|your|previous|prior)",
    r"you\s+are\s+now\s+(a\s+|an\s+|the\s+)?(DAN|free|unrestricted|new|different)",
    r"act\s+as\s+(a\s+|an\s+)?(different|new|another|evil|unrestricted|hacker|villain|dangerous|unfiltered|unlimited)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"(system\s+prompt|your\s+(prompt|instructions?|rules?|guidelines?))",
    r"do\s+anything\s+now",
    r"\b(developer|jailbreak|DAN|god)\s+mode\b",
    r"new\s+persona",
    r"(roleplay|role[\s-]play)\s+as",
    r"simulate\s+(being|a\s+|an\s+)",
    r"without\s+(any\s+)?(restrictions?|filters?|guidelines?|rules?|limits?|censorship)",
    r"(bypass|override|disable|remove|ignore)\s+(your\s+)?(safety|filter|restriction|limit|guideline|rule|constraint)",
    r"(in\s+this\s+)?hypothetical(ly)?\s+(scenario|speaking|world|universe|situation)",
    r"for\s+(educational|research|fictional|creative|story|hypothetical)\s+purposes?\s+(ignore|bypass|pretend)",
    r"<\s*(system|admin|root|prompt|instruction)\s*>",  # XML-style injection
    r"\[\[(system|admin|root|prompt)[^\]]*\]\]",         # bracket injection
]

# ---------------------------------------------------------------------------
# Layer 2 — Prompt injection (Vietnamese variants)
# ---------------------------------------------------------------------------

_INJECTION_VI = [
    r"bỏ\s+qua\s+(hướng\s+dẫn|quy\s+tắc|lệnh|chỉ\s+dẫn|giới\s+hạn)",
    r"quên\s+(tất\s+cả|hết|đi|hướng\s+dẫn|quy\s+tắc|lệnh)",
    r"(bây\s+giờ\s+)?bạn\s+(hãy\s+)?(là|trở\s+thành)\s+(một?\s+)?(AI|hacker|robot\s+khác|trợ\s+lý\s+khác)",
    r"giả\s+vờ\s+(là|bạn\s+là|như\s+bạn\s+là|rằng\s+bạn)",
    r"(hãy\s+)?không\s+(tuân\s+theo|theo|dùng)\s+(quy\s+tắc|hướng\s+dẫn|lệnh|giới\s+hạn)",
    r"không\s+có\s+(giới\s+hạn|hạn\s+chế|bộ\s+lọc|kiểm\s+duyệt|quy\s+tắc)",
    r"(vô\s+hiệu\s+hóa|tắt|bỏ|xóa)\s+(bộ\s+lọc|kiểm\s+duyệt|giới\s+hạn|an\s+toàn|quy\s+tắc)",
    r"(đóng\s+vai|nhập\s+vai|hóa\s+thân)\s+(là\s+)?(AI|robot|trợ\s+lý)?\s*(không\s+an\s+toàn|nguy\s+hiểm|ác|xấu|tự\s+do)",
    r"lệnh\s+(hệ\s+thống|ẩn|bí\s+mật|gốc)",
    r"(prompt|lệnh)\s+(gốc|thật|ẩn|hệ\s+thống)",
    r"chế\s+độ\s+(nhà\s+phát\s+triển|không\s+giới\s+hạn|tự\s+do|ẩn)",
]

# Compile once at import time
_HARM_RE = [re.compile(p, re.IGNORECASE) for p in _HARM_PATTERNS]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_EN + _INJECTION_VI]

# ---------------------------------------------------------------------------
# Gibberish / filler detection
# ---------------------------------------------------------------------------

_GIBBERISH_PATTERNS = [
    re.compile(r"^(ha){2,}[h]?$", re.IGNORECASE),
    re.compile(r"^(he){2,}[h]?$", re.IGNORECASE),
    re.compile(r"^(hi){2,}[h]?$", re.IGNORECASE),
    re.compile(r"^(hu){2,}[h]?$", re.IGNORECASE),
    re.compile(r"^(lol)+$", re.IGNORECASE),
    re.compile(r"^ok+e?$", re.IGNORECASE),
    re.compile(r"^ừ+$"),
    re.compile(r"^uh+$", re.IGNORECASE),
    re.compile(r"^[aeiouáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ]{3,}$"),
]

_MATH_EXPR_RE = re.compile(
    r"[\d\s\+\-\*\/\(\)\×\÷\.,]+"
    r"(?:[\+\-\*\/\×\÷\(\)][\d\s\(\)\.]+)+"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_injection_attempt(text: str) -> bool:
    """Return True if the text looks like a prompt injection attempt."""
    t = text.lower()
    return any(p.search(t) for p in _INJECTION_RE)


def is_harmful_content(text: str) -> bool:
    """Return True if the text contains harmful/inappropriate content."""
    t = text.lower()
    return any(p.search(t) for p in _HARM_RE)


def is_safe(text: str) -> bool:
    """Return False if text is harmful OR an injection attempt."""
    return not is_harmful_content(text) and not is_injection_attempt(text)


def is_meaningful_question(text: str) -> bool:
    """Return False for gibberish, filler words, or suspiciously short input."""
    stripped = text.strip()

    if len(stripped) < 5:
        return False

    if _MATH_EXPR_RE.fullmatch(stripped):
        return True

    words = stripped.split()
    if len(words) < 2:
        return False

    lower = stripped.lower()
    for pattern in _GIBBERISH_PATTERNS:
        if pattern.match(lower):
            return False

    if len(words) <= 3 and len(set(w.lower() for w in words)) == 1:
        return False

    return True
