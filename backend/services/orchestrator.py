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

    # 4. Query ngắn ≤ 3 từ, không phải tiếng Việt phổ thông và không phải math
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
            return OrchestrateResult(
                query_type=qtype,
                math_result=math_result,
                retrieval_status="rule_engine",
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
        result = await search_dictionary(message, direction="vi_to_tay_nung")
        return OrchestrateResult(
            query_type=qtype,
            dict_context=(result or {}).get("context") or None,
            retrieval_status=(result or {}).get(
                "retrieval_status", "no_relevant_context"
            ),
        )

    if qtype == QueryType.DICT_TAY_VI:
        result = await search_dictionary(message, direction="tay_to_vi")
        return OrchestrateResult(
            query_type=qtype,
            dict_context=(result or {}).get("context") or None,
            retrieval_status=(result or {}).get(
                "retrieval_status", "no_relevant_context"
            ),
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
        )

    # GENERAL — không search
    return OrchestrateResult(
        query_type=qtype,
        retrieval_status="no_relevant_context",
    )
