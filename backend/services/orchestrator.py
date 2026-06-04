"""
Orchestrator điều phối luồng xử lý câu hỏi:
- Phân loại QueryType từ message
- Route sang Rule Engine / vector_search / dictionary_search tương ứng
- Trả OrchestrateResult cho router build context + gọi LLM
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum

from backend.services.dictionary_search import search_dictionary
from backend.services.intent_detector import detect, solve
from backend.services.math_rules import MathResult
from backend.services.vector_search import search

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Math → dict query builder
# ---------------------------------------------------------------------------

_VI_NUMBERS: dict[int, str] = {
    0: "không", 1: "một", 2: "hai", 3: "ba", 4: "bốn", 5: "năm",
    6: "sáu", 7: "bảy", 8: "tám", 9: "chín", 10: "mười",
}

_OP_VI: dict[str, str] = {
    "addition":                   "cộng tổng",
    "subtraction":                "trừ hiệu",
    "multiplication":             "nhân tích",
    "division":                   "chia thương",
    "multiplication_table":       "bảng nhân",
    "division_table":             "bảng chia",
    "arithmetic_expression":      "tính",
    "rectangle_perimeter":        "chu vi chiều dài chiều rộng hình chữ nhật",
    "square_perimeter":           "chu vi cạnh hình vuông",
    "triangle_perimeter":         "chu vi cạnh tam giác",
    "rectangle_area":             "diện tích chiều dài chiều rộng hình chữ nhật",
    "square_area":                "diện tích cạnh hình vuông",
    "triangle_area":              "diện tích đáy chiều cao tam giác",
    "circle_circumference":       "chu vi bán kính đường kính hình tròn",
    "circle_area":                "diện tích bán kính hình tròn",
    "trapezoid_area":             "diện tích đáy chiều cao hình thang",
    "cube_volume":                "thể tích cạnh hình lập phương",
    "box_volume":                 "thể tích chiều dài chiều rộng chiều cao hình hộp",
    "length_conversion":          "đơn vị đo độ dài",
    "mass_conversion":            "đơn vị đo khối lượng",
    "time_conversion":            "đơn vị đo thời gian",
    "area_conversion":            "đơn vị đo diện tích",
    "speed_from_distance_time":   "vận tốc quãng đường thời gian",
    "distance_from_speed_time":   "quãng đường vận tốc thời gian",
    "time_from_distance_speed":   "thời gian quãng đường vận tốc",
    "percent_of_number":          "phần trăm",
    "find_percent_rate":          "tỉ số phần trăm",
    "find_original_from_percent": "số gốc phần trăm",
}


def _build_math_dict_query(formula_key: str, intent_params: dict) -> str:
    """
    Xây câu query tiếng Việt tự nhiên để tìm từ điển Tày/Nùng cho bài toán.
    Số nhỏ (0–10) → chữ tiếng Việt để reranker khớp dictionary entries.
    """
    op_terms = _OP_VI.get(formula_key, "toán học")
    num_words: list[str] = []

    if formula_key == "arithmetic_expression":
        # Extract tất cả số trong biểu thức, chuyển số ≤ 10 thành chữ
        expr = intent_params.get("expr", "")
        ops_in_expr: list[str] = []
        for op_char, op_vi in (("+", "cộng"), ("-", "trừ"), ("*", "nhân"), ("/", "chia")):
            if op_char in expr:
                ops_in_expr.append(op_vi)
        for raw in re.findall(r"\d+", expr):
            n = int(raw)
            if n in _VI_NUMBERS:
                num_words.append(_VI_NUMBERS[n])
        op_terms = " ".join(ops_in_expr) if ops_in_expr else "tính"
    else:
        for key in ("a", "b", "n"):
            val = intent_params.get(key)
            if val is not None:
                try:
                    n = int(float(val))
                    if n in _VI_NUMBERS:
                        num_words.append(_VI_NUMBERS[n])
                except (ValueError, TypeError):
                    pass

    # Bỏ trùng số trong num_words nhưng giữ thứ tự
    seen: set[str] = set()
    deduped: list[str] = []
    for w in num_words:
        if w not in seen:
            seen.add(w)
            deduped.append(w)

    parts = deduped + [op_terms] if deduped else [op_terms]
    return " ".join(parts)


class QueryType(Enum):
    MATH_CALCULATE = "math_calculate"   # bài tính → Rule Engine
    MATH_THEORY    = "math_theory"      # lý thuyết Toán → vector_search
    DICT_VI_TAY    = "dict_vi_tay"      # Việt → Tày/Nùng
    DICT_TAY_VI    = "dict_tay_vi"      # Tày → Việt
    MATH_WITH_DICT = "math_with_dict"   # Toán + kèm từ điển
    GENERAL        = "general"          # fallback


@dataclass
class OrchestrateResult:
    query_type: QueryType
    math_result: MathResult | None = None
    math_context: list[dict] | None = None
    dict_context: list[dict] | None = None
    retrieval_status: str = "no_relevant_context"
    best_dict_rerank: float = 0.0


# ---------------------------------------------------------------------------
# Từ khóa phân loại
# ---------------------------------------------------------------------------

_THEORY_TRIGGERS = (
    "là gì",
    "nghĩa là",
    "công thức",
    "cách tính",
    "giải thích",
    "tại sao",
    "như thế nào",
)

_MATH_KEYWORDS = (
    "toán", "hình", "phép",
    "diện tích", "chu vi", "thể tích",
    "tam giác", "hình vuông", "hình chữ nhật", "hình tròn", "hình thang",
    "hình lập phương", "hình hộp",
    "tỉ số", "phân số", "phần trăm", "số học", "lũy thừa",
    "phép cộng", "phép trừ", "phép nhân", "phép chia",
    "cộng", "trừ", "nhân", "chia",
    "số", "đo", "đơn vị",
    "vận tốc", "quãng đường", "thời gian", "tốc độ",
    "bảng nhân", "bảng chia", "cửu chương",
    "số thập phân", "số nguyên",
)

_DICT_VI_TAY_TRIGGERS = (
    "tiếng tày",
    "tiếng nùng",
    "tày là gì",
    "nùng là gì",
    "dịch sang tày",
    "dịch sang nùng",
    "bằng tiếng tày",
    "bằng tiếng nùng",
)

# Từ phổ thông tiếng Việt — sự hiện diện gợi ý "đây là tiếng Việt thường"
_VI_COMMON_WORDS = {
    "là", "của", "có", "cho", "với", "không", "được", "đã", "sẽ", "đang",
    "này", "đó", "ấy", "kia", "ai", "gì", "sao", "nào", "đâu",
    "tôi", "bạn", "em", "anh", "chị", "ông", "bà", "con", "mẹ", "bố", "cha",
    "thì", "mà", "nhưng", "và", "hoặc", "hay", "vì", "nếu", "khi",
    "trên", "dưới", "trong", "ngoài", "trước", "sau", "giữa",
    "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười",
    "to", "nhỏ", "lớn", "bé", "cao", "thấp",
    "đi", "về", "đến", "lên", "xuống",
    "ăn", "uống", "ngủ", "học", "chơi", "làm", "đọc", "viết",
    "đẹp", "tốt", "xấu", "ngon",
    "rồi", "chưa", "nữa", "lại",
    "nói", "hỏi", "trả", "lời",
}


def _has_any(text: str, triggers) -> bool:
    return any(trigger in text for trigger in triggers)


def _looks_like_common_vietnamese(text: str) -> bool:
    tokens = re.findall(r"\w+", text.lower())
    return any(tok in _VI_COMMON_WORDS for tok in tokens)


# ---------------------------------------------------------------------------
# Classify
# ---------------------------------------------------------------------------

def classify_query(message: str) -> QueryType:
    text = message.lower()

    # 1. Rule Engine → MATH_CALCULATE
    if detect(message):
        return QueryType.MATH_CALCULATE

    has_theory_trigger = _has_any(text, _THEORY_TRIGGERS)
    has_math_keyword = _has_any(text, _MATH_KEYWORDS)
    has_math_theory = has_theory_trigger and has_math_keyword
    has_dict_trigger = _has_any(text, _DICT_VI_TAY_TRIGGERS)

    # 2. Math lý thuyết + Tày/Nùng → MATH_WITH_DICT
    if has_math_theory and has_dict_trigger:
        return QueryType.MATH_WITH_DICT

    # 3. Tày/Nùng trigger → DICT_VI_TAY
    if has_dict_trigger:
        return QueryType.DICT_VI_TAY

    # 4a. "[từ] là gì?" — phân loại dựa vào subject:
    #   • subject chứa từ Việt phổ thông → DICT_VI_TAY (tìm nghĩa Tày/Nùng của từ Việt đó)
    #   • subject trông giống tiếng Tày (không quen) → DICT_TAY_VI
    m = re.match(r"^(.+?)\s+(?:là\s+gì|nghĩa\s+là\s+gì)\??\s*$", text)
    if m:
        subject_tokens = re.findall(r"\w+", m.group(1).strip())
        if subject_tokens and not _has_any(m.group(1), _MATH_KEYWORDS):
            is_vi_common = any(tok in _VI_COMMON_WORDS for tok in subject_tokens)
            if is_vi_common:
                return QueryType.DICT_VI_TAY
            else:
                return QueryType.DICT_TAY_VI

    # 4b. Query ngắn ≤ 3 từ, không phải tiếng Việt phổ thông và không phải math
    tokens = re.findall(r"\w+", text)
    if (
        1 <= len(tokens) <= 3
        and not _looks_like_common_vietnamese(text)
        and not has_math_keyword
    ):
        return QueryType.DICT_TAY_VI

    # 5. Math lý thuyết → MATH_THEORY
    if has_math_theory:
        return QueryType.MATH_THEORY

    # 6. Fallback
    return QueryType.GENERAL


# ---------------------------------------------------------------------------
# Trạng thái retrieval — chọn cái mạnh nhất khi merge nhiều nguồn
# ---------------------------------------------------------------------------

_STATUS_RANK = {
    "strong_context": 3,
    "medium_context": 2,
    "weak_context": 1,
    "no_relevant_context": 0,
}


def _best_status(statuses: list[str | None]) -> str:
    best = "no_relevant_context"
    for s in statuses:
        if s and _STATUS_RANK.get(s, 0) > _STATUS_RANK.get(best, 0):
            best = s
    return best


# ---------------------------------------------------------------------------
# Orchestrate
# ---------------------------------------------------------------------------

async def orchestrate(
    message: str,
    grade: int = 0,
    language: str = "vi",
    mode: str = "student",
) -> OrchestrateResult:
    qtype = classify_query(message)
    log.info(
        "[ORCHESTRATE] query=%r  type=%s  grade=%d  lang=%s  mode=%s",
        message,
        qtype.value,
        grade,
        language,
        mode,
    )

    if qtype == QueryType.MATH_CALCULATE:
        math_result = solve(message)
        if math_result and math_result.ok:
            # Build dict query từ tên phép tính + số (bảy, tám, nhân...)
            # thay vì raw query ("7 * 8 =?") để reranker khớp tốt hơn
            intent = detect(message)
            dict_query = (
                _build_math_dict_query(math_result.formula_key, intent.params)
                if intent else _OP_VI.get(math_result.formula_key, message)
            )
            log.info("[ORCHESTRATE] dict_query=%r (formula=%s)", dict_query, math_result.formula_key)
            dict_res = await search_dictionary(dict_query, direction="vi_to_tay_nung")
            return OrchestrateResult(
                query_type=qtype,
                math_result=math_result,
                dict_context=(dict_res or {}).get("context") or None,
                retrieval_status="rule_engine",
                best_dict_rerank=float((dict_res or {}).get("top_rerank_score", 0.0)),
            )
        # Rule Engine không giải được → fallback vector_search lấy lý thuyết Toán
        log.warning(
            "[ORCHESTRATE] MATH_CALCULATE failed (math_result=%r) → fallback vector_search",
            math_result,
        )
        result = await search(message, grade=grade)
        return OrchestrateResult(
            query_type=qtype,
            math_result=math_result,
            math_context=(result or {}).get("context") or None,
            retrieval_status=(result or {}).get(
                "retrieval_status", "no_relevant_context"
            ),
        )

    if qtype == QueryType.MATH_THEORY:
        result = await search(message, grade=grade)
        return OrchestrateResult(
            query_type=qtype,
            math_context=(result or {}).get("context") or None,
            retrieval_status=(result or {}).get(
                "retrieval_status", "no_relevant_context"
            ),
        )

    if qtype == QueryType.DICT_VI_TAY:
        # "both" để tìm cả tay_vi entries — nhiều từ chỉ có trong từ điển Tày→Việt
        result = await search_dictionary(message, direction="both")
        return OrchestrateResult(
            query_type=qtype,
            dict_context=(result or {}).get("context") or None,
            retrieval_status=(result or {}).get("retrieval_status", "no_relevant_context"),
            best_dict_rerank=float((result or {}).get("top_rerank_score", 0.0)),
        )

    if qtype == QueryType.DICT_TAY_VI:
        result = await search_dictionary(message, direction="both")
        return OrchestrateResult(
            query_type=qtype,
            dict_context=(result or {}).get("context") or None,
            retrieval_status=(result or {}).get("retrieval_status", "no_relevant_context"),
            best_dict_rerank=float((result or {}).get("top_rerank_score", 0.0)),
        )

    if qtype == QueryType.MATH_WITH_DICT:
        math_res, dict_res = await asyncio.gather(
            search(message, grade=grade),
            search_dictionary(message, direction="vi_to_tay_nung"),
        )
        statuses = [
            (math_res or {}).get("retrieval_status"),
            (dict_res or {}).get("retrieval_status"),
        ]
        return OrchestrateResult(
            query_type=qtype,
            math_context=(math_res or {}).get("context") or None,
            dict_context=(dict_res or {}).get("context") or None,
            retrieval_status=_best_status(statuses),
            best_dict_rerank=float((dict_res or {}).get("top_rerank_score", 0.0)),
        )

    # GENERAL — không search
    return OrchestrateResult(
        query_type=qtype,
        retrieval_status="no_relevant_context",
    )
