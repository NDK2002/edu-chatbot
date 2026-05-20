import json
import os

_dict: dict = {}

def load_dict(path: str = "data/hmong_viet_dict.json"):
    """Load từ điển Việt–H'Mông vào bộ nhớ."""
    global _dict
    if not _dict and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            _dict = json.load(f)

def hmong_to_vi(word: str) -> str | None:
    """Tra từ H'Mông → tiếng Việt."""
    load_dict()
    entry = _dict.get(word.lower())
    return entry["vi"] if entry else None

def vi_to_hmong(word: str) -> str | None:
    """Tra tiếng Việt → từ H'Mông (reverse lookup)."""
    load_dict()
    word_lower = word.lower()
    for hmong, entry in _dict.items():
        if entry.get("vi", "").lower() == word_lower:
            return hmong
    return None
