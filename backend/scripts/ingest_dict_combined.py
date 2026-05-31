#!/usr/bin/env python3
"""
ingest_dict_combined.py
=======================
Embed và nạp dictionary_combined.jsonl vào Qdrant collection edu_dictionary.

Thay thế ingest_dict.py (dùng cho 2 collection cũ riêng biệt).

Cách dùng:
    python -m backend.scripts.ingest_dict_combined
    python -m backend.scripts.ingest_dict_combined --dry-run   # kiểm tra mà không ghi
    python -m backend.scripts.ingest_dict_combined --recreate  # xoá và tạo lại collection
"""

import argparse
import hashlib
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
JSONL_PATH = ROOT / "data" / "chunks" / "dictionary_combined.jsonl"

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION = os.getenv("QDRANT_COLLECTION_DICT", "edu_dictionary")

AI_MODEL_API_KEY = os.getenv("AI_MODEL_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "AITeamVN/Vietnamese_Embedding")
EMBED_URL = os.getenv("EMBED_URL", "https://ai-model.ndk.id.vn/embeddings")

BATCH_SIZE = 50
MAX_RETRIES = 3

_headers = {"Authorization": f"Bearer {AI_MODEL_API_KEY}"}

# Payload indexes cho collection edu_dictionary
PAYLOAD_INDEXES: list[tuple[str, PayloadSchemaType]] = [
    ("direction", PayloadSchemaType.KEYWORD),        # tay_vi | vi_tay_nung
    ("source", PayloadSchemaType.KEYWORD),           # nguồn dữ liệu
    ("dialect", PayloadSchemaType.KEYWORD),          # phương ngữ
    ("quality_tier", PayloadSchemaType.KEYWORD),     # high | medium | low | community
    ("review_status", PayloadSchemaType.KEYWORD),    # academic_source_trusted | community_source_need_review
    ("content_type", PayloadSchemaType.KEYWORD),     # dictionary_entry
    ("vi_no_diacritics", PayloadSchemaType.KEYWORD), # tìm kiếm không dấu
]


# ── Embedding ──────────────────────────────────────────────────────────────────

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
        except httpx.HTTPError as e:
            if attempt == MAX_RETRIES:
                raise
            print(f"  ⚠ Embed lỗi (lần {attempt}): {e} — thử lại sau {attempt*2}s")
            time.sleep(attempt * 2)
    return []


def get_vector_dim() -> int:
    return len(embed_batch(["test"])[0])


# ── Point ID ───────────────────────────────────────────────────────────────────

def make_point_id(record: dict, line_no: int) -> int:
    """
    ID ổn định dựa trên hash của (direction, tay, vi).
    Fallback về line number nếu thiếu field.
    """
    key = f"{record.get('direction','')}|{record.get('tay','').lower()}|{record.get('vi','').lower()}"
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)
    return h % (2**53)  # Qdrant dùng uint64, JS safe integer limit


# ── Load records ───────────────────────────────────────────────────────────────

def load_records() -> list[dict]:
    if not JSONL_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy: {JSONL_PATH}")

    records = []
    with open(JSONL_PATH, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  ⚠ Dòng {i} JSON lỗi: {e}")
    return records


# ── Ingest ─────────────────────────────────────────────────────────────────────

def ingest(dry_run: bool = False, recreate: bool = False) -> None:
    print(f"📂 Đọc {JSONL_PATH.name} ...")
    records = load_records()
    print(f"  ✅ {len(records)} entries")

    # Thống kê nhanh
    directions = {}
    for r in records:
        d = r.get("direction", "?")
        directions[d] = directions.get(d, 0) + 1
    for d, c in directions.items():
        print(f"     {d}: {c}")

    if dry_run:
        print("\n🔍 Dry-run — không ghi vào Qdrant.")
        return

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Recreate hoặc upsert
    existing = [c.name for c in client.get_collections().collections]
    if recreate and COLLECTION in existing:
        client.delete_collection(COLLECTION)
        print(f"  🗑  Đã xoá collection cũ: {COLLECTION}")
        existing = [c for c in existing if c != COLLECTION]

    if COLLECTION not in existing:
        vector_dim = get_vector_dim()
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
        )
        print(f"  ✅ Tạo collection: {COLLECTION} (dim={vector_dim})")
    else:
        print(f"  ℹ  Collection đã tồn tại: {COLLECTION} — upsert tiếp")

    # Tạo payload indexes
    for field, schema in PAYLOAD_INDEXES:
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name=field,
            field_schema=schema,
        )
    print(f"  📑 Đã tạo {len(PAYLOAD_INDEXES)} payload indexes")

    # Upsert theo batch
    total = len(records)
    for i in range(0, total, BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        texts = [r["text"] for r in batch]
        vectors = embed_batch(texts)
        time.sleep(0.5)

        points = [
            PointStruct(
                id=make_point_id(r, i + j),
                vector=v,
                payload=r,
            )
            for j, (r, v) in enumerate(zip(batch, vectors))
        ]

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                client.upsert(collection_name=COLLECTION, points=points)
                break
            except Exception as e:
                if attempt == MAX_RETRIES:
                    raise
                print(f"  ⚠ Upsert lỗi (lần {attempt}): {e} — thử lại sau {attempt*2}s")
                time.sleep(attempt * 2)

        print(f"  ↑ {min(i + BATCH_SIZE, total)}/{total}")

    print(f"\n🎉 Xong: {total} entries → collection '{COLLECTION}'")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nạp dictionary_combined.jsonl vào Qdrant collection edu_dictionary."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Đọc file và thống kê, không ghi vào Qdrant",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Xoá collection cũ và tạo lại từ đầu",
    )
    args = parser.parse_args()

    ingest(dry_run=args.dry_run, recreate=args.recreate)


if __name__ == "__main__":
    main()
