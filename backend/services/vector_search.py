import logging
import os
import re
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

log = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION = os.getenv("QDRANT_COLLECTION_MATH", "edu_math")
VECTOR_THRESHOLD = float(os.getenv("VECTOR_SCORE_THRESHOLD", 0.40))
RERANK_THRESHOLD = float(os.getenv("RERANK_SCORE_THRESHOLD", 0.0))

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


def _query_qdrant(
    client: QdrantClient,
    vector: list[float],
    grade: int,
    top_k: int,
):
    response = client.query_points(
        collection_name=COLLECTION,
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
        scores = [0.0] * len(documents)
        for r in results:
            scores[r["index"]] = r["relevance_score"]
        return scores


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
        return None

    log.info("[SEARCH] Qdrant hits=%d  top3_scores=%s",
                len(hits),
                [f"{h.score:.4f}" for h in hits[:3]])

    # Stage 2: rerank
    valid_hits = [h for h in hits if h.payload]
    documents = [
        _metadata_value(h.payload, "content", _metadata_value(h.payload, "text", ""))
        for h in valid_hits
    ]
    rerank_scores = await _rerank(query, documents)
    ranked = sorted(zip(valid_hits, rerank_scores), key=lambda x: x[1], reverse=True)

    log.info("[SEARCH] rerank top3=%s",
                [(f"{sc:.4f}", _metadata_value(h.payload, "title", "")[:40])
                for h, sc in ranked[:3]])

    best_hit, best_rerank_score = ranked[0]
    if best_rerank_score < RERANK_THRESHOLD:
        log.info("[SEARCH] rerank best=%.4f < threshold=%.4f → None", best_rerank_score, RERANK_THRESHOLD)
        return None

    best_payload = best_hit.payload or {}
    best_title = _metadata_value(best_payload, "title", "")
    best_lesson_id = _lesson_id(best_payload)
    log.info("[SEARCH] best → title=%r  grade=%s  source=%s  rerank=%.4f id=%s point_id=%s",
                best_title,
                _metadata_value(best_payload, "grade"),
                _metadata_value(best_payload, "source_file"),
                best_rerank_score,
                best_lesson_id,
                best_hit.id)

    # Merge top chunks from the same lesson
    merged_parts = []
    seen_content: set[str] = set()
    for hit, _ in ranked[:6]:
        if not hit.payload:
            continue
        hit_payload = hit.payload
        if _lesson_id(hit_payload) != best_lesson_id:
            if _metadata_value(hit_payload, "title", "") != best_title:
                continue
        chunk = _metadata_value(
            hit_payload,
            "content",
            _metadata_value(hit_payload, "text", ""),
        ).strip()
        if chunk and chunk not in seen_content:
            merged_parts.append(chunk)
            seen_content.add(chunk)

    return {
        "content": "\n\n".join(merged_parts),
        "title": best_title,
        "grade": _metadata_value(best_payload, "grade"),
        "subject": _metadata_value(best_payload, "subject"),
        "book_set": _metadata_value(best_payload, "book_set"),
        "source_file": _metadata_value(
            best_payload,
            "source_file",
            _metadata_value(best_payload, "source_url"),
        ),
        "pages": _metadata_value(best_payload, "pages", []),
        "lesson_id": best_lesson_id,
        "score": float(best_rerank_score),
    }
