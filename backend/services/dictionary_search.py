"""
Dictionary search cho hai collection từ điển Tày/Nùng.

Tái sử dụng utilities từ vector_search (embed, rerank, classify, dedupe,
hit→context, client) — KHÔNG copy code.

Direction:
- vi_to_tay_nung : Việt → Tày/Nùng (COLLECTION_VI_TAY)
- tay_to_vi      : Tày → Việt (COLLECTION_TAY_VI)
- both           : song song cả 2 collection, merge kết quả
"""

import asyncio
import logging

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from backend.services.vector_search import (
    _embed,
    _rerank,
    get_client,
    _headers,  # noqa: F401  (giữ import theo spec, dùng gián tiếp qua _embed/_rerank)
    _hit_to_dictionary_context,
    classify_retrieval_score,
    _select_context_limit,
    _dedupe_contexts,
    COLLECTION_VI_TAY,
    COLLECTION_TAY_VI,
)

log = logging.getLogger(__name__)


def _build_dict_filter() -> Filter:
    return Filter(
        must=[FieldCondition(key="domain", match=MatchValue(value="dictionary"))]
    )


def _payload_get(payload: dict, key, default=None):
    if key in payload and payload.get(key) is not None:
        return payload.get(key)
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and key in metadata:
        return metadata.get(key, default)
    return default


def _hit_content(hit) -> str:
    """Trích text từ payload để rerank."""
    payload = hit.payload or {}

    content = _payload_get(payload, "content")
    if content:
        return str(content).strip()

    vi = _payload_get(payload, "vi", "") or ""
    tay = _payload_get(payload, "tay", "") or ""
    tay_variants = _payload_get(payload, "tay_variants", []) or []
    nung_variants = _payload_get(payload, "nung_variants", []) or []

    if tay and vi:
        return f"{tay} = {vi}"

    parts = []
    if vi:
        parts.append(f"Việt: {vi}")
    if tay_variants:
        tay_str = (
            ", ".join(tay_variants)
            if isinstance(tay_variants, list)
            else str(tay_variants)
        )
        parts.append(f"Tày: {tay_str}")
    if nung_variants:
        nung_str = (
            ", ".join(nung_variants)
            if isinstance(nung_variants, list)
            else str(nung_variants)
        )
        parts.append(f"Nùng: {nung_str}")
    if tay and not vi:
        parts.append(f"Tày: {tay}")

    return "; ".join(parts)


async def _search_one_collection(
    query: str,
    vector: list[float],
    collection_name: str,
    top_k: int,
) -> tuple[list, list[float]]:
    """Query 1 collection từ điển, trả (valid_hits, rerank_scores)."""
    client: QdrantClient = get_client()
    response = client.query_points(
        collection_name=collection_name,
        query=vector,
        limit=top_k,
        query_filter=_build_dict_filter(),
        with_payload=True,
    )
    hits = response.points

    if not hits:
        log.info("[DICT_SEARCH] %s → 0 hits", collection_name)
        return [], []

    log.info(
        "[DICT_SEARCH] %s hits=%d  top3_vector=%s",
        collection_name,
        len(hits),
        [f"{h.score:.4f}" for h in hits[:3]],
    )

    valid_hits = [h for h in hits if h.payload and _hit_content(h)]
    if not valid_hits:
        log.info("[DICT_SEARCH] %s → no valid hits with content", collection_name)
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
    """
    log.info(
        "[DICT_SEARCH] query=%r  direction=%s  top_k=%d",
        query,
        direction,
        top_k,
    )

    vector = await _embed(query)

    if direction == "vi_to_tay_nung":
        valid_hits, rerank_scores = await _search_one_collection(
            query, vector, COLLECTION_VI_TAY, top_k
        )
    elif direction == "tay_to_vi":
        valid_hits, rerank_scores = await _search_one_collection(
            query, vector, COLLECTION_TAY_VI, top_k
        )
    elif direction == "both":
        (hits_vt, scores_vt), (hits_tv, scores_tv) = await asyncio.gather(
            _search_one_collection(query, vector, COLLECTION_VI_TAY, top_k),
            _search_one_collection(query, vector, COLLECTION_TAY_VI, top_k),
        )
        valid_hits = list(hits_vt) + list(hits_tv)
        rerank_scores = list(scores_vt) + list(scores_tv)
    else:
        raise ValueError(f"Unsupported direction: {direction!r}")

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
    retrieval_status = classify_retrieval_score(
        vector_score=best_vector_score,
        rerank_score=best_rerank_score,
    )

    log.info(
        "[DICT_SEARCH] status=%s  best_vector=%.4f  best_rerank=%.4f  total_hits=%d",
        retrieval_status,
        best_vector_score,
        best_rerank_score,
        len(valid_hits),
    )

    context_limit = _select_context_limit(retrieval_status)
    # Cho "both" cho phép gấp đôi để giữ kết quả từ cả 2 collection
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
