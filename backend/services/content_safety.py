import re

BLOCKED_PATTERNS = [
    r"\b(hack|cheat|bypass|jailbreak)\b",
    r"(bạo lực|giết|đánh nhau|vũ khí|chém|đâm|nổ|khủng bố|tấn công|xả súng|đánh bom)",
    r"thằng chó|đồ chó|đồ đĩ|đồ con lợn|đồ con chó|đồ con đĩ|đồ con cặc|đồ con lồn",
    r"con chim|con cặc|đụ mẹ|đụ bố|đụ con|đụ vợ|đụ gái|đụ lồn|đụ em|đụ anh|đụ chị",
    r"(sex|sexual|nude|porn|xxx|dâm|địt|lồn|cặc|đụ|đéo|đĩ|gái gọi)",
    r"\b(drug|cocaine|heroin|meth|weed|marijuana|thuốc lắc|ma túy|chất cấm)\b",
    r"kill|suicide|self[- ]?harm|tự tử|tự sát|tự hại",
    r"(phim|ảnh)\s*(18\+|người lớn|khiêu dâm)",
    r"(thuốc|ma túy|chất cấm)",
    # Prompt injection attempts
    r"ignore (previous|all|prior) instruction",
    r"(forget|disregard) (everything|all|what)",
    r"you are now",
    r"act as (a |an )?(different|new|another|evil|unrestricted)",
    r"pretend (you are|to be)",
    r"(system prompt|your prompt|your instruction)",
    r"do anything now",
    r"developer mode",
]

_GIBBERISH_PATTERNS = [
    r"^(ha){2,}[h]?$",
    r"^(he){2,}[h]?$",
    r"^(hi){2,}[h]?$",
    r"^(hu){2,}[h]?$",
    r"^(lol)+$",
    r"^ok+e?$",
    r"^ừ+$",
    r"^uh+$",
    r"^[aeiouáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ]{3,}$",
]


def is_safe(text: str) -> bool:
    text_lower = text.lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return False
    return True


def is_meaningful_question(text: str) -> bool:
    """Return False for gibberish, filler words, or suspiciously short input."""
    stripped = text.strip()

    if len(stripped) < 5:
        return False

    _MATH_EXPR_RE = re.compile(
        r"[\d\s\+\-\*\/\(\)\×\÷\.,]+"
        r"(?:[\+\-\*\/\×\÷\(\)][\d\s\(\)\.]+)+"
    )
    
    if _MATH_EXPR_RE.fullmatch(stripped):
        return True

    words = stripped.split()
    if len(words) < 2:
        return False

    lower = stripped.lower()
    for pattern in _GIBBERISH_PATTERNS:
        if re.match(pattern, lower):
            return False

    # All words identical → "haha haha" / "oke oke"
    if len(words) <= 3 and len(set(w.lower() for w in words)) == 1:
        return False

    return True
