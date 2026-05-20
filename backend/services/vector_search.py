import os
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from google import genai
from google.genai import types

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION  = os.getenv("QDRANT_COLLECTION", "edu_kb")
THRESHOLD   = float(os.getenv("VECTOR_SCORE_THRESHOLD", 0.82))

_qdrant: QdrantClient | None = None
_genai_client: genai.Client | None = None


def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _qdrant


def _get_genai() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _genai_client


async def embed(text: str) -> list[float]:
    """Tạo embedding bằng Gemini text-embedding-004."""
    client = _get_genai()
    result = client.models.embed_content(
        model="text-embedding-004",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return list(result.embeddings[0].values)


async def search(query: str, grade: int = 0, top_k: int = 3) -> dict | None:
    """
    Tìm kiếm trong Qdrant. Trả về kết quả tốt nhất nếu score >= THRESHOLD.
    """
    vector = await embed(query)
    client = _get_qdrant()

    query_filter = None
    if grade > 0:
        query_filter = Filter(
            must=[FieldCondition(key="grade", match=MatchValue(value=grade))]
        )

    hits = client.search(
        collection_name=COLLECTION,
        query_vector=vector,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    if not hits:
        return None

    best = hits[0]
    if best.score < THRESHOLD:
        return None

    return {
        "content": best.payload.get("content", ""),
        "title":   best.payload.get("title", ""),
        "score":   best.score,
    }
