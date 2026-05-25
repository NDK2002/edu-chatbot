"""
Intent detector đơn giản cho Toán tiểu học lớp 1–5.
Dùng regex + keyword matching — không LLM, không ML.

Flow: detect(query) → Intent(rule_fn, params) | None
        solve(query)  → MathResult | None   (shortcut gọi detect rồi execute)
"""

import logging
import re
from dataclasses import dataclass, field

from backend.services.math_rules import RULES, MathResult

log = logging.getLogger(__name__)


@dataclass
class Intent:
    rule_fn: str        # tên hàm trong RULES
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Số và đơn vị
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"\d+(?:[,\.]\d+)?")

_UNIT_LEN = {"mm", "cm", "dm", "m", "km"}
_UNIT_MASS = {"mg", "g", "kg", "tấn", "tan"}
_UNIT_AREA = {"mm²", "cm²", "dm²", "m²", "km²", "ha", "a"}
_UNIT_TIME = {"giây", "phút", "giờ", "ngày"}

_UNIT_LEN_RE = re.compile(r"\b(\d+(?:[,\.]\d+)?)\s*(mm|cm|dm|km|m)\b", re.IGNORECASE)
_UNIT_MASS_RE = re.compile(r"\b(\d+(?:[,\.]\d+)?)\s*(mg|kg|tấn|tan|g)\b", re.IGNORECASE)
_UNIT_TIME_RE = re.compile(r"\b(\d+(?:[,\.]\d+)?)\s*(giây|phút|giờ|ngày)\b", re.IGNORECASE)
_UNIT_AREA_RE = re.compile(r"\b(\d+(?:[,\.]\d+)?)\s*(mm²|cm²|dm²|m²|km²|ha|a)\b", re.IGNORECASE)


def _n(s: str) -> float:
    return float(s.replace(",", "."))


def _nums(text: str) -> list[float]:
    return [_n(m) for m in _NUM_RE.findall(text)]


def _first_unit(text: str, unit_set: set[str], unit_re: re.Pattern) -> str | None:
    m = unit_re.search(text)
    return m.group(2).lower() if m else None


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[×x✕]", "×", text)
    text = re.sub(r"[÷:]", "÷", text)
    text = re.sub(r"\s+", " ", text)
    return text


# ---------------------------------------------------------------------------
# Detectors — mỗi hàm trả Intent | None
# ---------------------------------------------------------------------------

def _detect_table(q: str) -> Intent | None:
    m = re.search(r"bảng\s+(nhân|cửu\s+chương)\s+(\d+)", q)
    if m:
        return Intent("multiplication_table", {"n": int(m.group(2))})
    m = re.search(r"bảng\s+chia\s+(\d+)", q)
    if m:
        return Intent("division_table", {"n": int(m.group(1))})
    return None


def _detect_basic_arithmetic(q: str) -> Intent | None:
    # Dạng "số op số [đơn vị]" — ưu tiên phát hiện phép tính tường minh
    m = re.search(r"(\d+(?:[,\.]\d+)?)\s*\+\s*(\d+(?:[,\.]\d+)?)", q)
    if m:
        unit = _first_unit(q, _UNIT_LEN, _UNIT_LEN_RE) or \
                _first_unit(q, _UNIT_MASS, _UNIT_MASS_RE) or ""
        return Intent("addition", {"a": _n(m.group(1)), "b": _n(m.group(2)), "unit": unit})

    m = re.search(r"(\d+(?:[,\.]\d+)?)\s*[-−]\s*(\d+(?:[,\.]\d+)?)", q)
    if m:
        unit = _first_unit(q, _UNIT_LEN, _UNIT_LEN_RE) or \
                _first_unit(q, _UNIT_MASS, _UNIT_MASS_RE) or ""
        return Intent("subtraction", {"a": _n(m.group(1)), "b": _n(m.group(2)), "unit": unit})

    m = re.search(r"(\d+(?:[,\.]\d+)?)\s*×\s*(\d+(?:[,\.]\d+)?)", q)
    if m:
        return Intent("multiplication", {"a": _n(m.group(1)), "b": _n(m.group(2))})

    m = re.search(r"(\d+(?:[,\.]\d+)?)\s*÷\s*(\d+(?:[,\.]\d+)?)", q)
    if m:
        return Intent("division", {"a": _n(m.group(1)), "b": _n(m.group(2))})

    # Dạng chữ: "nhân", "chia", "cộng", "trừ"
    m = re.search(r"(\d+(?:[,\.]\d+)?)\s+nhân\s+(\d+(?:[,\.]\d+)?)", q)
    if m:
        return Intent("multiplication", {"a": _n(m.group(1)), "b": _n(m.group(2))})
    m = re.search(r"(\d+(?:[,\.]\d+)?)\s+chia\s+(\d+(?:[,\.]\d+)?)", q)
    if m:
        return Intent("division", {"a": _n(m.group(1)), "b": _n(m.group(2))})
    m = re.search(r"(\d+(?:[,\.]\d+)?)\s+cộng\s+(\d+(?:[,\.]\d+)?)", q)
    if m:
        return Intent("addition", {"a": _n(m.group(1)), "b": _n(m.group(2))})
    m = re.search(r"(\d+(?:[,\.]\d+)?)\s+trừ\s+(\d+(?:[,\.]\d+)?)", q)
    if m:
        return Intent("subtraction", {"a": _n(m.group(1)), "b": _n(m.group(2))})

    return None


def _detect_perimeter(q: str) -> Intent | None:
    if "chu vi" not in q:
        return None
    nums = _nums(q)
    unit = _first_unit(q, _UNIT_LEN, _UNIT_LEN_RE) or "cm"

    if "hình tròn" in q or "đường tròn" in q:
        if len(nums) >= 1:
            return Intent("circle_circumference", {"radius": nums[0], "unit": unit})

    if "hình chữ nhật" in q:
        if len(nums) >= 2:
            return Intent("rectangle_perimeter",
                            {"length": nums[0], "width": nums[1], "unit": unit})

    if "hình vuông" in q:
        if len(nums) >= 1:
            return Intent("square_perimeter", {"side": nums[0], "unit": unit})

    if "hình tam giác" in q or "tam giác" in q:
        if len(nums) >= 3:
            return Intent("triangle_perimeter",
                            {"a": nums[0], "b": nums[1], "c": nums[2], "unit": unit})
        if len(nums) == 1:
            # Tam giác đều
            return Intent("triangle_perimeter",
                            {"a": nums[0], "b": nums[0], "c": nums[0], "unit": unit})

    return None


def _detect_area(q: str) -> Intent | None:
    if "diện tích" not in q:
        return None
    nums = _nums(q)
    unit = _first_unit(q, _UNIT_LEN, _UNIT_LEN_RE) or "cm"

    if "hình tròn" in q or "đường tròn" in q:
        if len(nums) >= 1:
            return Intent("circle_area", {"radius": nums[0], "unit": unit})

    if "hình thang" in q:
        if len(nums) >= 3:
            return Intent("trapezoid_area",
                            {"a": nums[0], "b": nums[1], "height": nums[2], "unit": unit})

    if "hình chữ nhật" in q:
        if len(nums) >= 2:
            return Intent("rectangle_area",
                            {"length": nums[0], "width": nums[1], "unit": unit})

    if "hình vuông" in q:
        if len(nums) >= 1:
            return Intent("square_area", {"side": nums[0], "unit": unit})

    if "hình tam giác" in q or "tam giác" in q:
        if len(nums) >= 2:
            return Intent("triangle_area",
                            {"base": nums[0], "height": nums[1], "unit": unit})

    return None


def _detect_volume(q: str) -> Intent | None:
    if "thể tích" not in q:
        return None
    nums = _nums(q)
    unit = _first_unit(q, _UNIT_LEN, _UNIT_LEN_RE) or "cm"

    if "lập phương" in q:
        if len(nums) >= 1:
            return Intent("cube_volume", {"side": nums[0], "unit": unit})

    if "hộp chữ nhật" in q or "hình hộp" in q:
        if len(nums) >= 3:
            return Intent("box_volume",
                            {"length": nums[0], "width": nums[1], "height": nums[2], "unit": unit})

    return None


def _labeled_num(q: str, *labels: str) -> float | None:
    """Tìm số đứng ngay sau một trong các label."""
    for label in labels:
        m = re.search(rf"{label}\s+(\d+(?:[,\.]\d+)?)", q)
        if m:
            return _n(m.group(1))
    return None


def _detect_speed(q: str) -> Intent | None:
    has_speed = any(k in q for k in ("vận tốc", "tốc độ"))
    has_dist  = any(k in q for k in ("quãng đường", "khoảng cách"))
    has_time  = any(k in q for k in ("thời gian", "mất", "đi hết"))

    if not (has_speed or has_dist or has_time):
        return None

    d_unit = _first_unit(q, _UNIT_LEN, _UNIT_LEN_RE) or "km"
    t_unit = _first_unit(q, _UNIT_TIME, _UNIT_TIME_RE) or "giờ"

    # Extract giá trị gắn với label để tránh nhầm thứ tự số
    speed    = _labeled_num(q, "vận tốc", "tốc độ")
    distance = _labeled_num(q, "quãng đường", "khoảng cách")
    time     = _labeled_num(q, "thời gian", "mất", "đi hết")

    find_time  = re.search(r"(thời gian|mất|đi hết)[^?]{0,20}(bao nhiêu|\?)", q)
    find_dist  = re.search(r"(quãng đường|khoảng cách)[^?]{0,20}(bao nhiêu|\?)", q)
    find_speed = re.search(r"(vận tốc|tốc độ)[^?]{0,20}(bao nhiêu|\?)", q)

    if find_time and distance is not None and speed is not None:
        return Intent("time_from_distance_speed",
                        {"distance": distance, "speed": speed,
                        "d_unit": d_unit, "t_unit": t_unit})

    if find_dist and speed is not None and time is not None:
        return Intent("distance_from_speed_time",
                        {"speed": speed, "time": time,
                        "s_unit": d_unit, "t_unit": t_unit})

    if (find_speed or not find_time) and distance is not None and time is not None:
        return Intent("speed_from_distance_time",
                        {"distance": distance, "time": time,
                        "d_unit": d_unit, "t_unit": t_unit})

    return None


def _detect_percent(q: str) -> Intent | None:
    # "X% của Y" — tìm giá trị
    m = re.search(r"(\d+(?:[,\.]\d+)?)\s*%\s*(?:của|trong)\s+(\d+(?:[,\.]\d+)?)", q)
    if m:
        return Intent("percent_of_number",
                        {"number": _n(m.group(2)), "percent": _n(m.group(1))})

    # "X là bao nhiêu % của Y" — tìm tỉ số
    if re.search(r"bao nhiêu\s*%", q) or "tỉ số phần trăm" in q:
        nums = _nums(q)
        if len(nums) >= 2:
            return Intent("find_percent_rate", {"part": nums[0], "whole": nums[1]})

    # "Y là X%, tìm số gốc / tổng số"
    if re.search(r"số\s+gốc|tổng\s+số|tất\s+cả", q):
        m = re.search(r"(\d+(?:[,\.]\d+)?)[^\d]*(\d+(?:[,\.]\d+)?)\s*%", q)
        if m:
            return Intent("find_original_from_percent",
                            {"part": _n(m.group(1)), "percent": _n(m.group(2))})

    return None


def _detect_unit_conversion(q: str) -> Intent | None:
    # Pattern: "X đơn_vị [đổi/sang/=] Y đơn_vị" hoặc "X đơn_vị bằng bao nhiêu đơn_vị"
    conv_keywords = ("đổi", "chuyển", "bằng bao nhiêu", "= ?", "sang", "thành")
    if not any(k in q for k in conv_keywords):
        return None

    nums = _nums(q)
    if not nums:
        return None
    value = nums[0]

    # Tìm 2 đơn vị trong câu
    len_units = _UNIT_LEN_RE.findall(q)
    mass_units = _UNIT_MASS_RE.findall(q)
    time_units = _UNIT_TIME_RE.findall(q)
    area_units = _UNIT_AREA_RE.findall(q)

    if len(len_units) >= 2:
        return Intent("length_conversion",
                        {"value": value, "from_unit": len_units[0][1], "to_unit": len_units[1][1]})
    if len(mass_units) >= 2:
        return Intent("mass_conversion",
                        {"value": value, "from_unit": mass_units[0][1], "to_unit": mass_units[1][1]})
    if len(time_units) >= 2:
        return Intent("time_conversion",
                        {"value": value, "from_unit": time_units[0][1], "to_unit": time_units[1][1]})
    if len(area_units) >= 2:
        return Intent("area_conversion",
                        {"value": value, "from_unit": area_units[0][1], "to_unit": area_units[1][1]})

    # Nếu chỉ có 1 đơn vị nguồn, tìm đơn vị đích trong văn bản
    if len_units:
        from_u = len_units[0][1]
        m = re.search(r"sang\s+(mm|cm|dm|m|km)\b", q, re.IGNORECASE)
        if m:
            return Intent("length_conversion",
                            {"value": value, "from_unit": from_u, "to_unit": m.group(1)})
    if mass_units:
        from_u = mass_units[0][1]
        m = re.search(r"sang\s+(mg|g|kg|tấn)\b", q, re.IGNORECASE)
        if m:
            return Intent("mass_conversion",
                            {"value": value, "from_unit": from_u, "to_unit": m.group(1)})

    return None


# ---------------------------------------------------------------------------
# Thứ tự ưu tiên: cụ thể trước, chung chung sau
# ---------------------------------------------------------------------------

_DETECTORS = [
    _detect_table,
    _detect_perimeter,
    _detect_area,
    _detect_volume,
    _detect_speed,
    _detect_percent,
    _detect_unit_conversion,
    _detect_basic_arithmetic,   # cuối cùng — dễ bắt nhầm
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect(query: str) -> Intent | None:
    """Phân tích query, trả Intent nếu là bài tính, None nếu là câu hỏi lý thuyết."""
    q = _normalize(query)
    for detector in _DETECTORS:
        result = detector(q)
        if result:
            log.debug("[INTENT] detector=%s  rule=%s  params=%s",
                      detector.__name__, result.rule_fn, result.params)
            return result
    log.debug("[INTENT] no match → theory/RAG")
    return None


def solve(query: str) -> MathResult | None:
    """Shortcut: detect intent rồi gọi Rule Engine. Trả None nếu không phải bài tính."""
    intent = detect(query)
    if not intent:
        return None
    fn = RULES.get(intent.rule_fn)
    if not fn:
        return None
    try:
        return fn(**intent.params)  # type: ignore[operator]
    except (TypeError, ValueError):
        return None
