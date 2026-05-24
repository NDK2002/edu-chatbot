"""
ingest_qdrant.py
================
Nạp dữ liệu từ JSONL chunks vào Qdrant.

Cách dùng (chạy 1 lần sau khi crawl xong):
    python -m backend.scripts.ingest_qdrant --input data/chunks/sgk_chunks.jsonl
    python -m backend.scripts.ingest_qdrant --input data/chunks/hmong_viet_chunks.jsonl
"""

import argparse
import json
import os
import time
from dotenv import load_dotenv


import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION = os.getenv("QDRANT_COLLECTION_MATH", "edu_math")
AI_MODEL_API_KEY = os.getenv("AI_MODEL_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "AITeamVN/Vietnamese_Embedding")
EMBED_URL = os.getenv("EMBED_URL", "https://ai-model.ndk.id.vn/embeddings")

_headers = {"Authorization": f"Bearer {AI_MODEL_API_KEY}"}
MAX_RETRIES = 3

PAYLOAD_INDEXES: list[tuple[str, PayloadSchemaType]] = [
    ("grade", PayloadSchemaType.INTEGER),
    ("subject", PayloadSchemaType.KEYWORD),
    ("book_set", PayloadSchemaType.KEYWORD),
    ("source_file", PayloadSchemaType.KEYWORD),
    ("volume", PayloadSchemaType.KEYWORD),
    ("title", PayloadSchemaType.KEYWORD),
    ("content_type", PayloadSchemaType.KEYWORD),
    ("formula_key", PayloadSchemaType.KEYWORD),
    ("review_status", PayloadSchemaType.KEYWORD),
]


def embed_batch(texts: list[str]) -> list[list[float]]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = httpx.post(
                EMBED_URL,
                headers=_headers,
                json={"model": EMBED_MODEL, "input": texts},
                timeout=60,
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda x: x["index"])
            return [d["embedding"] for d in data]
        except httpx.HTTPError:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(attempt * 2)
    return []  # unreachable, satisfies type checker


def get_vector_dim() -> int:
    result = embed_batch(["test"])
    return len(result[0])


def _metadata_value(chunk: dict, key: str, default=None):
    if key in chunk and chunk.get(key) is not None:
        return chunk.get(key)

    metadata = chunk.get("metadata")
    if isinstance(metadata, dict):
        return metadata.get(key, default)

    return default


def _build_payload(chunk: dict) -> dict:
    return {
        "id": chunk["id"],
        "text": chunk["text"],
        "content": chunk["text"],
        "book_set": _metadata_value(chunk, "book_set", ""),
        "grade": _metadata_value(chunk, "grade", 0),
        "subject": _metadata_value(chunk, "subject", ""),
        "volume": _metadata_value(chunk, "volume"),
        "source_file": _metadata_value(chunk, "source_file", ""),
        "title": _metadata_value(chunk, "title", ""),
        "content_type": _metadata_value(chunk, "content_type", ""),
        "formula_key": _metadata_value(chunk, "formula_key"),
        "keywords": _metadata_value(chunk, "keywords", []),
        "table_number": _metadata_value(chunk, "table_number"),
        "start_page": _metadata_value(chunk, "start_page"),
        "end_page": _metadata_value(chunk, "end_page"),
        "review_status": _metadata_value(chunk, "review_status", ""),
        "source_type": _metadata_value(chunk, "source_type", ""),
    }


def ingest(input_path: str):
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Create collection if not exists
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        vector_dim = get_vector_dim()
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
        )
        print(f"✅ Created collection: {COLLECTION} (dim={vector_dim})")

    for field_name, field_schema in PAYLOAD_INDEXES:
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name=field_name,
            field_schema=field_schema,
        )

    # Read chunks
    chunks = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))
    print(f"📄 {len(chunks)} chunks from {input_path}")

    # Upsert in batches of 50
    BATCH = 50
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        texts = [
            "\n".join(filter(None, [
                _metadata_value(c, "title", ""),
                " ".join(_metadata_value(c, "keywords", []) or []),
                c["text"],
            ]))
            for c in batch
        ]

        vectors = embed_batch(texts)

        time.sleep(2)

        points = [
            PointStruct(
                id=abs(hash(c["id"])) % (10**9),
                vector=v,
                payload=_build_payload(c),
            )
            for c, v in zip(batch, vectors)
        ]
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                client.upsert(collection_name=COLLECTION, points=points)
                break
            except Exception:
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(attempt * 2)
        print(f"  ↑ {i + len(batch)}/{len(chunks)}")

    print(f"🎉 Completed ingest {len(chunks)} chunks into Qdrant")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    ingest(args.input)
