import logging
import os
import re
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

log = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION_MATH = os.getenv("QDRANT_COLLECTION_MATH", "edu_math")
COLLECTION_VI_TAY = os.getenv("QDRANT_COLLECTION_VI_TAY", "edu_vi_tay_nung_dictionary")
COLLECTION_TAY_VI = os.getenv("QDRANT_COLLECTION_TAY_VI", "edu_tay_vi_dictionary")
VECTOR_THRESHOLD = float(os.getenv("VECTOR_SCORE_THRESHOLD", 0.45))
RERANK_THRESHOLD = float(os.getenv("RERANK_SCORE_THRESHOLD", 0.80))

AI_MODEL_API_KEY = os.getenv("AI_MODEL_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "AITeamVN/Vietnamese_Embedding")
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
EMBED_URL = os.getenv("EMBED_URL", "https://ai-model.ndk.id.vn/embeddings")
RERANK_URL = os.getenv("RERANK_URL", "https://ai-model.ndk.id.vn/rerank")

_client = None

QUERY_EXPANSIONS: dict[str, str] = {
    "đặt tính nhân": "phép nhân đặt tính thực hiện",
    "đặt tính chia": "phép chia đặt tính thực hiện",
    "đặt tính cộng": "phép cộng đặt tính thực hiện",
    "đặt tính trừ": "phép trừ đặt tính thực hiện",
    "cách tính": "phương pháp thực hiện phép tính",
    "làm thế nào": "phương pháp cách thực hiện",
    "tính nhanh": "tính nhẩm tính nhanh phép tính",
}

SUBJECT_FILTER = "Toán"
BOOK_SET_FILTER = "Cánh Diều"


def expand_query(query: str) -> str:
    extra: list[str] = []
    q_lower = query.lower()
    for phrase, expansion in QUERY_EXPANSIONS.items():
        if phrase in q_lower:
            extra.append(expansion)
    return f"{query} {' '.join(extra)}".strip() if extra else query


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return _client


def _headers() -> dict:
    return {"Authorization": f"Bearer {AI_MODEL_API_KEY}"}


def _metadata_value(payload: dict, key: str, default=None):
    if key in payload and payload.get(key) is not None:
        return payload.get(key)

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return metadata.get(key, default)

    return default


def _lesson_id(payload: dict) -> str | None:
    lesson_id = _metadata_value(payload, "lesson_id")
    if lesson_id:
        return lesson_id

    chunk_id = _metadata_value(payload, "id")
    if not isinstance(chunk_id, str):
        return None

    return re.sub(r"_chunk_\d+$", "", chunk_id)


def _build_query_filter(grade: int) -> Filter:
    must: list[FieldCondition] = [
        FieldCondition(key="subject", match=MatchValue(value=SUBJECT_FILTER)),
        FieldCondition(key="book_set", match=MatchValue(value=BOOK_SET_FILTER)),
    ]
    if grade > 0:
        must.append(FieldCondition(key="grade", match=MatchValue(value=grade)))
    return Filter(must=must)

def classify_retrieval_score(vector_score: float, rerank_score: float | None) -> str:
    if rerank_score is not None:
        if rerank_score >= RERANK_THRESHOLD:
            return "strong_context"
        
        if rerank_score >= RERANK_THRESHOLD - 0.30:
            return "medium_context"
        
        if rerank_score >= RERANK_THRESHOLD - 0.60:
            return "weak_context"
        
        return "no_relevant_context"

    if vector_score >= VECTOR_THRESHOLD:
        return "strong_context"

    if vector_score >= VECTOR_THRESHOLD - 0.10:
        return "medium_context"

    if vector_score >= VECTOR_THRESHOLD - 0.20:
        return "weak_context"

    return "no_relevant_context"

def _select_context_limit(retrieval_status: str) -> int:
    if retrieval_status == "strong_context":
        return 3

    if retrieval_status == "medium_context":
        return 2
    
    if retrieval_status == "weak_context":
        return 1
    
    return 0

def _hit_to_math_context(hit, rerank_score: float | None) -> dict:
    payload = hit.payload or {}

    content = _metadata_value(
        payload,
        "content",
        _metadata_value(payload, "text", "")).strip()

    return {
        "type": "math_context",
        "content": content,
        "title": _metadata_value(payload, "title", ""),
        "grade": _metadata_value(payload, "grade"),
        "book_set": _metadata_value(payload, "book_set"),
        "source_file": _metadata_value(
            payload,
            "source_file",
            _metadata_value(payload, "source_url", ""),
        ),
        "pages": _metadata_value(payload, "pages", []),
        "lesson_id": _lesson_id(payload),
        "formula_key": _metadata_value(payload, "formula_key"),
        "content_type": _metadata_value(payload, "content_type"),
        "review_status": _metadata_value(payload, "review_status"),
        "source_type": _metadata_value(payload, "source_type"),
        "vector_score": float(hit.score or 0.0),
        "rerank_score": float(rerank_score or 0.0),
        "point_id": str(hit.id),
    }

def _hit_to_dictionary_context(hit, rerank_score: float | None = None) -> dict:
    payload = hit.payload or {}

    vi = _metadata_value(payload, "vi", "")
    tay_variants = _metadata_value(payload, "tay_variants", [])
    nung_variants = _metadata_value(payload, "nung_variants", [])

    content = _metadata_value(payload, "content", "").strip()
    if not content:
        content = (
            f"Từ tiếng Việt: {vi}.\n"
            f"Từ tiếng Tày: {', '.join(tay_variants) if isinstance(tay_variants, list) else tay_variants}\n"
            f"Từ tiếng Nùng: {', '.join(nung_variants) if isinstance(nung_variants, list) else nung_variants}"
        )
    
    return {
        "type": "dictionary_context",
        "content": content,
        "direction": _metadata_value(payload, "direction"),
        "vi": vi,
        "tay_variants": tay_variants,
        "nung_variants": nung_variants,
        "topic": _metadata_value(payload, "topic"),
        "dialect_note": _metadata_value(payload, "dialect_note"),
        "source_file": _metadata_value(payload, "source_file"),
        "review_status": _metadata_value(payload, "review_status"),
        "source_type": _metadata_value(payload, "source_type"),
        "vector_score": float(hit.score or 0.0),
        "rerank_score": float(rerank_score or 0.0),
        "point_id": str(hit.id),
    }

def _hit_to_context(hit, rerank_score: float, context_type: str) -> dict:
    if context_type == "math":
        return _hit_to_math_context(hit, rerank_score)

    if context_type == "dictionary":
        return _hit_to_dictionary_context(hit, rerank_score)

    raise ValueError(f"Unsupported context_type: {context_type}")

def _normalize_text_for_dedupe(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text

def _dedupe_contexts(contexts: list[dict]) -> list[dict]:
    sorted_contexts = sorted(
        contexts, 
        key=lambda c: (c.get("content") or "").strip(),
        reverse=True)

    result: list[dict] = []
    seen_contents: list[str] = []

    for ctx in sorted_contexts:
        content = ctx.get("content") or ""
        normalized = _normalize_text_for_dedupe(content)

        if not normalized:
            continue

        is_duplicate = any(
            normalized == seen or normalized in seen
            for seen in seen_contents
        )

        if is_duplicate:
            continue

        seen_contents.append(normalized)
        result.append(ctx)

    result.sort(
        key=lambda ctx: float(ctx.get("rerank_score") or 0.0),
        reverse=True,
    )
    
    return result

def _query_qdrant(
    client: QdrantClient,
    vector: list[float],
    grade: int,
    top_k: int,
):
    response = client.query_points(
        collection_name=COLLECTION_MATH,
        query=vector,
        limit=top_k,
        query_filter=_build_query_filter(grade),
        with_payload=True,
    )
    return response.points


async def _embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            EMBED_URL,
            headers=_headers(),
            json={"model": EMBED_MODEL, "input": text},
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


async def _rerank(query: str, documents: list[str]) -> list[float]:
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            RERANK_URL,
            headers=_headers(),
            json={"model": RERANK_MODEL, "query": query, "documents": documents},
        )
        resp.raise_for_status()
        results = resp.json()["results"]
        rerank_scores = [0.0] * len(documents)
        for r in results:
            rerank_scores[r["index"]] = r["relevance_score"]
        return rerank_scores


async def search(query: str, grade: int = 0, top_k: int = 40) -> dict | None:
    expanded = expand_query(query)
    grade_info = f"grade={grade}" if grade > 0 else "grade=all"
    log.info("[SEARCH] query=%r  %s  top_k=%d", query, grade_info, top_k)
    if expanded != query:
        log.debug("[SEARCH] expanded=%r", expanded)

    # Stage 1: vector retrieval
    vector = await _embed(expanded)
    client = get_client()

    hits = _query_qdrant(client, vector, grade, top_k)

    if not hits:
        log.info("[SEARCH] Qdrant returned 0 hits")
        return {
            "retrieval_status": "no_relevant_context",
            "content": [],
            "top_vector_scores": 0.0,
            "top_rerank_scores": None,
        }

    log.info("[SEARCH] Qdrant hits=%d  top3_vector_scores=%s",
                len(hits),
                [f"{h.score:.4f}" for h in hits[:3]])

    # Stage 2: prepare documents for reranking
    valid_hits = [
        h
        for h in hits
        if h.payload
        and _metadata_value(
            h.payload,
            "content",
            _metadata_value(h.payload, "text", ""),
        )
    ]

    if not valid_hits:
        log.info("[SEARCH] No valid hits with content for reranking")
        return {
            "retrieval_status": "no_relevant_context",
            "content": [],
            "top_vector_scores": float(hits[0].score or 0.0),
            "top_rerank_scores": None,
        }

    documents = [
        _metadata_value(
            h.payload,
            "content",
            _metadata_value(h.payload, "text", ""),
        )
        for h in valid_hits
    ]

    rerank_scores = await _rerank(query, documents)

    ranked = sorted(
        zip(valid_hits, rerank_scores),
        key=lambda x: x[1],
        reverse=True,
    )
    log.info(
        "[SEARCH] Rerank top3=%s",
        [
            (f"{sc:.4f}", _metadata_value(h.payload, "title", "")[:40])
            for h, sc in ranked[:3]
        ], 
    )

    best_hit, best_rerank_score = ranked[0]
    best_vector_score = float(best_hit.score or 0.0)
    retrieval_status = classify_retrieval_score(
        vector_score=best_vector_score, 
        rerank_score=best_rerank_score
    )

    best_payload = best_hit.payload or {}
    best_title = _metadata_value(best_payload, "title", "")

    log.info(
        "[SEARCH] status=%s best_vector=%.4f best_rerank=%.4f title=%r grade=%s source=%s point_id=%s",
        retrieval_status,
        best_vector_score,
        best_rerank_score,
        best_title,
        _metadata_value(best_payload, "grade"),
        _metadata_value(best_payload, "source_file"),
        best_hit.id
    )

    context_limit = _select_context_limit(retrieval_status)
    if context_limit <= 0:
        return {
            "retrieval_status": retrieval_status,
            "context": [],
            "top_vector_score": best_vector_score,
            "top_rerank_score": float(best_rerank_score),
        }

    contexts = [
        _hit_to_math_context(hit, rerank_score)
        for hit, rerank_score in ranked[:context_limit]
    ]

    contexts = _dedupe_contexts(contexts)

    return {
        "retrieval_status": retrieval_status,
        "context": contexts,
        "top_vector_score": best_vector_score,
        "top_rerank_score": float(best_rerank_score),
    }
