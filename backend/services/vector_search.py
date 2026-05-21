from glob import glob
import os
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from langchain_google_genai import GoogleGenerativeAIEmbeddings

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION = os.getenv("QDRANT_COLLECTION", "edu_kb")
THRESHOLD = float(os.getenv("VECTOR_SCORE_THRESHOLD", 0.82))

_client = None

embeddings_doc = GoogleGenerativeAIEmbeddings(
    google_api_key=os.getenv("GEMINI_API_KEY"),
    model="gemini-embedding-001",
    task_type="retrieval_document",
)
embeddings_query = GoogleGenerativeAIEmbeddings(
    google_api_key=os.getenv("GEMINI_API_KEY"),
    model="gemini-embedding-001",
    task_type="retrieval_query",
)


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    return _client


async def search(query: str, grade: int = 0, top_k: int = 3) -> dict | None:
    ## Use retrieval_query to embed question
    vector = embeddings_query.embed_query(query)
    client = get_client()

    query_filter = None
    if grade > 0:
        query_filter = Filter(
            must=[FieldCondition(key="grade", match=MatchValue(value=grade))]
        )

    hits = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    ).points

    if not hits:
        return None

    best = hits[0]
    print(f"DEBUG score: {best.score}")
    if best.score < THRESHOLD:
        return None

    ## Check payload before access
    if not best.payload:
        return None

    return {
        "content": best.payload.get("content", ""),
        "title": best.payload.get("title", ""),
        "score": best.score,
    }
