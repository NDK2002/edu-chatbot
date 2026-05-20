import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import google.generativeai as genai

QDRANT_HOST  = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT  = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION   = os.getenv("QDRANT_COLLECTION", "edu_kb")
THRESHOLD    = float(os.getenv("VECTOR_SCORE_THRESHOLD", 0.82))

_client = None

def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _client

async def embed(text: str) -> list[float]:
    """Tạo embedding bằng Gemini embedding model."""
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_query",
    )
    return result["embedding"]

async def search(query: str, grade: int = 0, top_k: int = 3) -> dict | None:
    """
    Tìm kiếm trong Qdrant. Trả về kết quả tốt nhất nếu score >= THRESHOLD.
    """
    vector = await embed(query)
    client = get_client()

    # Filter theo lớp nếu có
    query_filter = None
    if grade > 0:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
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
