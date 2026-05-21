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
from pathlib import Path
from dotenv import load_dotenv


from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION = os.getenv("QDRANT_COLLECTION", "edu_kb")
VECTOR_DIM = 3072

embeddings = GoogleGenerativeAIEmbeddings(
    google_api_key=os.getenv("GEMINI_API_KEY"),
    model="gemini-embedding-001",
    task_type="retrieval_document",
)


def ingest(input_path: str):
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Create collection if not exists
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        print(f"✅ Created collection: {COLLECTION}")

    client.create_payload_index(
        collection_name=COLLECTION,
        field_name="grade",
        field_schema=PayloadSchemaType.INTEGER,
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
        texts = [c["content"] for c in batch]

        vectors = embeddings.embed_documents(texts)

        time.sleep(2)

        points = [
            PointStruct(
                id=abs(hash(c["id"])) % (10**9),
                vector=v,
                payload={
                    "id": c["id"],
                    "title": c.get("title", ""),
                    "content": c["content"],
                    "subject": c.get("subject", ""),
                    "grade": c.get("grade", 0),
                    "source_url": c.get("source_url", ""),
                },
            )
            for c, v in zip(batch, vectors)
        ]
        client.upsert(collection_name=COLLECTION, points=points)
        print(f"  ↑ {i + len(batch)}/{len(chunks)}")

    print(f"🎉 Completed ingest {len(chunks)} chunks into Qdrant")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    ingest(args.input)
