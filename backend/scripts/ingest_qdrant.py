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

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import google.generativeai as genai

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION  = os.getenv("QDRANT_COLLECTION", "edu_kb")
VECTOR_DIM  = 768   # text-embedding-004

def embed_batch(texts: list[str]) -> list[list[float]]:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    results = []
    for text in texts:
        r = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
        )
        results.append(r["embedding"])
        time.sleep(0.1)  # tránh rate limit
    return results

def ingest(input_path: str):
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Tạo collection nếu chưa có
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        print(f"✅ Tạo collection: {COLLECTION}")

    # Đọc chunks
    chunks = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))
    print(f"📄 {len(chunks)} chunks từ {input_path}")

    # Upsert theo batch 50
    BATCH = 50
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i+BATCH]
        texts = [c["content"] for c in batch]
        vectors = embed_batch(texts)

        points = [
            PointStruct(
                id=abs(hash(c["id"])) % (10**9),
                vector=v,
                payload={
                    "id":         c["id"],
                    "title":      c.get("title", ""),
                    "content":    c["content"],
                    "subject":    c.get("subject", ""),
                    "grade":      c.get("grade", 0),
                    "source_url": c.get("source_url", ""),
                },
            )
            for c, v in zip(batch, vectors)
        ]
        client.upsert(collection_name=COLLECTION, points=points)
        print(f"  ↑ {i+len(batch)}/{len(chunks)}")

    print(f"🎉 Hoàn tất ingest {len(chunks)} chunks vào Qdrant")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    ingest(args.input)
