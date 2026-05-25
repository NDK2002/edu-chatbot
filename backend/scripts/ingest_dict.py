#!/usr/bin/env python3
"""
ingest_dict.py
==============
Embed và nạp từ điển JSONL vào Qdrant.

Chạy SAU khi đã chạy parse_dict.py.

Cách dùng:
    python -m backend.scripts.ingest_dict --collection vi_tay_nung
    python -m backend.scripts.ingest_dict --collection tay_vi
    python -m backend.scripts.ingest_dict --collection both   (mặc định)
"""

import argparse
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent.parent
CHUNKS_DIR = ROOT / "data" / "chunks"

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
AI_MODEL_API_KEY = os.getenv("AI_MODEL_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "AITeamVN/Vietnamese_Embedding")
EMBED_URL = os.getenv("EMBED_URL", "https://ai-model.ndk.id.vn/embeddings")

COLLECTION_VI_TAY = "edu_vi_tay_nung_dictionary"
COLLECTION_TAY_VI = "edu_tay_vi_dictionary"

BATCH_SIZE = 50
MAX_RETRIES = 3

_headers = {"Authorization": f"Bearer {AI_MODEL_API_KEY}"}

# Payload indexes cho từng collection
INDEXES_VI_TAY: list[tuple[str, PayloadSchemaType]] = [
    ("domain", PayloadSchemaType.KEYWORD),
    ("direction", PayloadSchemaType.KEYWORD),
    ("topic", PayloadSchemaType.KEYWORD),
    ("vi_no_accent", PayloadSchemaType.KEYWORD),
    ("review_status", PayloadSchemaType.KEYWORD),
    ("source_file", PayloadSchemaType.KEYWORD),
]

INDEXES_TAY_VI: list[tuple[str, PayloadSchemaType]] = [
    ("domain", PayloadSchemaType.KEYWORD),
    ("direction", PayloadSchemaType.KEYWORD),
    ("tay_norm", PayloadSchemaType.KEYWORD),
    ("tay_no_accent", PayloadSchemaType.KEYWORD),
    ("review_status", PayloadSchemaType.KEYWORD),
    ("source_file", PayloadSchemaType.KEYWORD),
]


# ── Embedding ─────────────────────────────────────────────────────────────────

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
    return []


def get_vector_dim() -> int:
    return len(embed_batch(["test"])[0])


# ── Qdrant point ID ───────────────────────────────────────────────────────────

def _point_id(rec: dict) -> int:
    """
    Stable integer ID cho Qdrant point.
    vi_tay_nung_XXXXX → 1_000_000 + XXXXX
    tay_vi_XXXXX      → 2_000_000 + XXXXX
    """
    rid = rec["id"]
    if rid.startswith("vi_tay_nung_"):
        return 1_000_000 + int(rid.split("_")[-1])
    if rid.startswith("tay_vi_"):
        return 2_000_000 + int(rid.split("_")[-1])
    return abs(hash(rid)) % (10**9)


# ── Ingest ────────────────────────────────────────────────────────────────────

def ingest_collection(
    jsonl_path: Path,
    collection_name: str,
    indexes: list[tuple[str, PayloadSchemaType]],
) -> None:
    if not jsonl_path.exists():
        print(f"⛔ File không tìm thấy: {jsonl_path}")
        print("   Hãy chạy parse_dict.py trước.")
        return

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Tạo collection nếu chưa có
    existing = [c.name for c in client.get_collections().collections]
    if collection_name not in existing:
        vector_dim = get_vector_dim()
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
        )
        print(f"  ✅ Tạo collection: {collection_name} (dim={vector_dim})")
    else:
        print(f"  ℹ  Collection đã tồn tại: {collection_name} — upsert tiếp")

    # Tạo payload indexes
    for field, schema in indexes:
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field,
            field_schema=schema,
        )

    # Đọc records
    records = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    print(f"  📄 {len(records)} records từ {jsonl_path.name}")

    # Upsert theo batch
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        vectors = embed_batch([r["text"] for r in batch])
        time.sleep(1)

        points = [
            PointStruct(id=_point_id(r), vector=v, payload=r)
            for r, v in zip(batch, vectors)
        ]
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                client.upsert(collection_name=collection_name, points=points)
                break
            except Exception:
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(attempt * 2)

        print(f"  ↑ {i + len(batch)}/{len(records)}")

    print(f"  🎉 Xong: {len(records)} records → {collection_name}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embed và nạp từ điển JSONL vào Qdrant."
    )
    parser.add_argument(
        "--collection",
        choices=["vi_tay_nung", "tay_vi", "both"],
        default="both",
        help="Collection cần nạp (mặc định: both)",
    )
    args = parser.parse_args()

    if args.collection in ("vi_tay_nung", "both"):
        print(f"\n📤 Ingesting → {COLLECTION_VI_TAY}")
        ingest_collection(
            CHUNKS_DIR / "dict_vi_tay_nung.jsonl",
            COLLECTION_VI_TAY,
            INDEXES_VI_TAY,
        )

    if args.collection in ("tay_vi", "both"):
        print(f"\n📤 Ingesting → {COLLECTION_TAY_VI}")
        ingest_collection(
            CHUNKS_DIR / "dict_tay_vi.jsonl",
            COLLECTION_TAY_VI,
            INDEXES_TAY_VI,
        )


if __name__ == "__main__":
    main()
