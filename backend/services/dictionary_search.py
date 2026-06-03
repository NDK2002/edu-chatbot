"""
Dictionary search cho collection từ điển Tày/Nùng (single collection edu_dictionary).

Tái sử dụng utilities từ vector_search (embed, rerank, classify, dedupe,
hit→context, client) — KHÔNG copy code.

Direction (giá trị trong payload):
- vi_tay_nung : Việt → Tày/Nùng
- tay_vi      : Tày → Việt

Caller (orchestrator) truyền vào:
- "vi_to_tay_nung" → map thành payload direction "vi_tay_nung"
- "tay_to_vi"      → map thành payload direction "tay_vi"
- "both"           → không filter direction, tìm toàn bộ collection
"""

import logging
import os
import re as _re

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from backend.services.vector_search import (
    _embed,
    _rerank,
    get_client,
    _hit_to_dictionary_context,
    classify_retrieval_score,
    _select_context_limit,
    _dedupe_contexts,
    COLLECTION_DICT,
)

# Dictionary dùng threshold thấp hơn — reranker score với dict entry thường 0.15–0.50
# base=0.60 → weak nếu score >= 0.0, medium >= 0.30, strong >= 0.60
RERANK_DICT_THRESHOLD = float(os.getenv("RERANK_DICT_THRESHOLD", "0.60"))

log = logging.getLogger(__name__)

# Direction strings khớp trực tiếp với payload — không cần map
_VALID_DIRECTIONS: set[str] = {"vi_to_tay_nung", "tay_to_vi", "both"}

_QUESTION_SUFFIX_RE = _re.compile(
    r"\s+(?:là\s+gì|nghĩa\s+là\s+gì|có\s+nghĩa\s+là\s+gì)\s*\??\s*$",
    _re.IGNORECASE,
)


def _build_embed_query(query: str, payload_direction: str | None) -> str:
    """
    Strip question suffixes ('là gì?') trước khi embed.
    Khi direction='both', append 'tiếng Tày Nùng' để kéo vector về
    gần vi_tay_nung entries (được index theo tiếng Việt).
    """
    stripped = _QUESTION_SUFFIX_RE.sub("", query.strip()).strip() or query.strip()
    if payload_direction is None:  # "both"
        return f"{stripped} tiếng Tày Nùng"
    return stripped


def _build_dict_filter(payload_direction: str | None = None) -> Filter:
    """
    Filter cho collection edu_dictionary.
    Nếu payload_direction được truyền, filter thêm theo direction.
    """
    conditions: list[FieldCondition] = []  # word_chunk & topic_chunk đều hợp lệ
    if payload_direction:
        conditions.append(
            FieldCondition(key="direction", match=MatchValue(value=payload_direction))
        )
    return Filter(must=conditions)


def _first_variant(raw: str) -> str:
    """Lấy biến thể đầu tiên — bỏ ghi chú phương ngữ trong dấu ngoặc."""
    if not raw:
        return ""
    for sep in ("(", ";", "\n"):
        raw = raw.split(sep)[0]
    return raw.strip()


def _hit_content(hit) -> str:
    """Trích text từ payload để rerank.

    vi_tay_nung: xây câu tự nhiên có 'tiếng Tày/Nùng' để reranker khớp tốt hơn
        với các query dạng 'X tiếng Tày là gì'.
    tay_vi:      dùng text field gốc (đã ngắn gọn).
    """
    payload = hit.payload or {}
    direction = payload.get("direction", "")

    if direction == "vi_tay_nung":
        vi = (payload.get("vi") or "").strip()
        tay_first = _first_variant(payload.get("tay") or "")
        nung_first = _first_variant(payload.get("nung") or "")
        parts: list[str] = []
        if tay_first:
            parts.append(f"tiếng Tày là {tay_first}")
        if nung_first:
            parts.append(f"tiếng Nùng là {nung_first}")
        if parts:
            return f"{vi}: {'; '.join(parts)}."
        return vi

    if direction == "tay_vi":
        vi = (payload.get("vi") or "").strip()
        tay = (payload.get("tay") or "").strip()
        # Bỏ chỉ số đồng âm "(2)", "(3)" ở cuối tay headword
        import re as _re
        tay_clean = _re.sub(r"\s*\(\d+\)\s*$", "", tay).strip()
        if vi and tay_clean:
            return f"{vi}: tiếng Tày là {tay_clean}."

    # Fallback: dùng text field gốc
    text = payload.get("text", "") or ""
    if text:
        return text.split("\n[search:")[0].strip()
    tay = payload.get("tay", "") or ""
    vi = payload.get("vi", "") or ""
    if tay and vi:
        return f"{tay} = {vi}"
    return (tay or vi).strip()


async def _search_collection(
    query: str,
    vector: list[float],
    payload_direction: str | None,
    top_k: int,
) -> tuple[list, list[float]]:
    """Query edu_dictionary, lọc theo direction nếu có. Trả (valid_hits, rerank_scores)."""
    client: QdrantClient = get_client()
    response = client.query_points(
        collection_name=COLLECTION_DICT,
        query=vector,
        limit=top_k,
        query_filter=_build_dict_filter(payload_direction),
        with_payload=True,
    )
    hits = response.points

    if not hits:
        log.info("[DICT_SEARCH] direction=%s → 0 hits", payload_direction or "both")
        return [], []

    log.info(
        "[DICT_SEARCH] direction=%s  hits=%d  top3_vector=%s",
        payload_direction or "both",
        len(hits),
        [f"{h.score:.4f}" for h in hits[:3]],
    )

    valid_hits = [h for h in hits if h.payload and _hit_content(h)]
    if not valid_hits:
        log.info("[DICT_SEARCH] direction=%s → no valid hits", payload_direction or "both")
        return [], []

    documents = [_hit_content(h) for h in valid_hits]
    rerank_scores = await _rerank(query, documents)
    return valid_hits, rerank_scores


async def search_dictionary(
    query: str,
    direction: str = "vi_to_tay_nung",
    top_k: int = 20,
) -> dict | None:
    """
    Search từ điển theo direction. Trả về dict:
      {
        retrieval_status, context, top_vector_score, top_rerank_score
      }

    direction nhận: "vi_to_tay_nung", "tay_to_vi", "both"
    """
    log.info(
        "[DICT_SEARCH] query=%r  direction=%s  top_k=%d",
        query,
        direction,
        top_k,
    )

    _MISSING = object()
    if direction == "both":
        payload_direction = None  # không filter direction → tìm cả 2
    else:
        if direction not in _VALID_DIRECTIONS:
            raise ValueError(f"Unsupported direction: {direction!r}")
        payload_direction = direction  # khớp trực tiếp với payload field

    embed_query = _build_embed_query(query, payload_direction)
    vector = await _embed(embed_query)

    valid_hits, rerank_scores = await _search_collection(
        query, vector, payload_direction, top_k
    )

    if not valid_hits:
        return {
            "retrieval_status": "no_relevant_context",
            "context": [],
            "top_vector_score": 0.0,
            "top_rerank_score": 0.0,
        }

    ranked = sorted(
        zip(valid_hits, rerank_scores),
        key=lambda x: x[1],
        reverse=True,
    )

    best_hit, best_rerank_score = ranked[0]
    best_vector_score = float(best_hit.score or 0.0)

    # Token fallback: khi cụm từ Tày/Nùng không khớp (rerank quá thấp),
    # search từng token riêng để trả nghĩa từng từ
    keyword = _QUESTION_SUFFIX_RE.sub("", query.strip()).strip()
    tokens = keyword.split()
    if best_rerank_score < 0.10 and len(tokens) >= 2:
        log.info("[DICT_SEARCH] rerank=%.4f → token fallback for %d tokens", best_rerank_score, len(tokens))
        token_hits: list = []
        token_scores: list[float] = []
        seen_ids: set = set()
        for tok in tokens[:4]:  # giới hạn 4 token
            tok_vec = await _embed(f"{tok} tiếng Tày Nùng")
            t_hits, t_scores = await _search_collection(tok, tok_vec, payload_direction, top_k=5)
            for h, s in zip(t_hits, t_scores):
                hit_id = getattr(h, "id", None)
                if hit_id not in seen_ids and s >= 0.10:
                    seen_ids.add(hit_id)
                    token_hits.append(h)
                    token_scores.append(s)
        if token_hits:
            ranked = sorted(zip(token_hits, token_scores), key=lambda x: x[1], reverse=True)
            best_hit, best_rerank_score = ranked[0]
            best_vector_score = float(best_hit.score or 0.0)
            log.info("[DICT_SEARCH] token fallback found %d results", len(token_hits))

    retrieval_status = classify_retrieval_score(
        vector_score=best_vector_score,
        rerank_score=best_rerank_score,
        rerank_threshold=RERANK_DICT_THRESHOLD,
    )

    log.info(
        "[DICT_SEARCH] status=%s  best_vector=%.4f  best_rerank=%.4f  total_hits=%d",
        retrieval_status,
        best_vector_score,
        best_rerank_score,
        len(valid_hits),
    )

    context_limit = _select_context_limit(retrieval_status)
    # "both" trả kết quả từ cả 2 direction → cho phép gấp đôi
    if direction == "both" and context_limit > 0:
        context_limit = context_limit * 2

    if context_limit <= 0:
        return {
            "retrieval_status": retrieval_status,
            "context": [],
            "top_vector_score": best_vector_score,
            "top_rerank_score": float(best_rerank_score),
        }

    contexts = [
        _hit_to_dictionary_context(hit, rerank_score)
        for hit, rerank_score in ranked[:context_limit]
    ]
    contexts = _dedupe_contexts(contexts)

    return {
        "retrieval_status": retrieval_status,
        "context": contexts,
        "top_vector_score": best_vector_score,
        "top_rerank_score": float(best_rerank_score),
    }
