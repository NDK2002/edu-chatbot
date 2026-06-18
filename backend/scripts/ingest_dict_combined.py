#!/usr/bin/env python3
"""
ingest_dict_combined.py
=======================
Embed và nạp dictionary_v2.jsonl vào Qdrant collection edu_dictionary.

dictionary_v2.jsonl gồm 3 loại chunks:
  - word_chunk (vi_to_tay_nung) : community data, 1 từ = 1 chunk
  - topic_chunk (vi_to_tay_nung): community data, 1 chủ đề = 1 chunk
  - word_chunk (tay_to_vi)      : Lương Bèn, 1 từ = 1 chunk

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
JSONL_PATH = ROOT / "data" / "chunks" / "dictionary_v2.jsonl"

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION = os.getenv("QDRANT_COLLECTION_DICT", "edu_dictionary")

EMBED_MODEL = os.getenv("EMBED_MODEL", "AITeamVN/Vietnamese_Embedding")
EMBED_URL = os.getenv("EMBED_URL", "https://ai-model.ndk.id.vn/embeddings")
AI_MODEL_API_KEY = os.getenv("AI_MODEL_API_KEY", "")

_headers = {"Authorization": f"Bearer {AI_MODEL_API_KEY}"}

BATCH_SIZE = 8   # nhỏ để tránh timeout trên server CPU
MAX_RETRIES = 3
EMBED_TIMEOUT = 180  # CPU inference chậm, cần timeout dài hơn 60s

# Fallback local model — chỉ load khi remote API fail hết MAX_RETRIES lần
_local_model = None


def _get_local_model():
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer
        print(f"  ⚠ Remote API không khả dụng — tải local model {EMBED_MODEL} ...")
        _local_model = SentenceTransformer(EMBED_MODEL)
        print("  ✅ Local model loaded (fallback mode)")
    return _local_model

# Payload indexes cho collection edu_dictionary
PAYLOAD_INDEXES: list[tuple[str, PayloadSchemaType]] = [
    ("direction", PayloadSchemaType.KEYWORD),           # vi_to_tay_nung | tay_to_vi
    ("content_type", PayloadSchemaType.KEYWORD),        # word_chunk | topic_chunk
    ("source", PayloadSchemaType.KEYWORD),              # nguồn dữ liệu
    ("quality_tier", PayloadSchemaType.KEYWORD),        # high | medium | low | community
    ("review_status", PayloadSchemaType.KEYWORD),       # academic_source_trusted | community_source_need_review
    ("vi_no_diacritics", PayloadSchemaType.KEYWORD),    # tìm kiếm không dấu theo vi
    ("topic_no_diacritics", PayloadSchemaType.KEYWORD), # tìm kiếm không dấu theo topic
    ("topic", PayloadSchemaType.KEYWORD),               # chủ đề (có dấu)
]


# ── Embedding ──────────────────────────────────────────────────────────────────

def embed_batch(texts: list[str]) -> list[list[float]]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = httpx.post(
                EMBED_URL,
                headers=_headers,
                json={"model": EMBED_MODEL, "input": texts},
                timeout=EMBED_TIMEOUT,
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda x: x["index"])
            return [d["embedding"] for d in data]
        except Exception as e:
            if attempt == MAX_RETRIES:
                print(f"  ⚠ Remote embed thất bại sau {MAX_RETRIES} lần ({e}) — chuyển sang local model")
                print("  ⚠ Cảnh báo: load local model (~2.3GB) có thể OOM nếu infinity containers đang chạy trên server ít RAM")
                model = _get_local_model()
                return model.encode(texts, show_progress_bar=False).tolist()
            time.sleep(attempt * 2)
    return []  # unreachable


def get_vector_dim(hint: int | None = None) -> int:
    if hint:
        return hint
    # thử remote trước
    try:
        resp = httpx.post(
            EMBED_URL,
            headers=_headers,
            json={"model": EMBED_MODEL, "input": ["test"]},
            timeout=30,
        )
        resp.raise_for_status()
        return len(resp.json()["data"][0]["embedding"])
    except Exception:
        return _get_local_model().get_sentence_embedding_dimension()


# ── Point ID ───────────────────────────────────────────────────────────────────

def make_point_id(record: dict, line_no: int) -> int:
    """
    ID ổn định dựa trên hash của (content_type, direction, tay, vi, topic).
    topic_chunk dùng thêm topic để phân biệt với word_chunk cùng vi.
    """
    content_type = record.get("content_type", "word_chunk")
    direction    = record.get("direction", "")
    tay          = record.get("tay", "").lower()
    vi           = record.get("vi", "").lower()
    topic        = record.get("topic", "").lower()
    key = f"{content_type}|{direction}|{tay}|{vi}|{topic}"
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)
    return h % (2**53)


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

def ingest(dry_run: bool = False, recreate: bool = False, vector_dim_hint: int | None = None) -> None:
    print(f"📂 Đọc {JSONL_PATH.name} ...")
    records = load_records()
    print(f"  ✅ {len(records)} entries")

    # Thống kê nhanh
    directions   = {}
    chunk_types  = {}
    for r in records:
        d = r.get("direction", "?")
        c = r.get("content_type", "?")
        directions[d]  = directions.get(d, 0) + 1
        chunk_types[c] = chunk_types.get(c, 0) + 1
    for d, n in directions.items():
        print(f"     {d}: {n}")
    for c, n in chunk_types.items():
        print(f"     {c}: {n}")

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
        vector_dim = get_vector_dim(vector_dim_hint)
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

    # Checkpoint — lưu tiến độ để resume khi crash
    checkpoint_path = JSONL_PATH.parent / f".ingest_checkpoint_{COLLECTION}.txt"
    start_idx = 0
    if not recreate and checkpoint_path.exists():
        try:
            start_idx = int(checkpoint_path.read_text().strip())
            print(f"  ▶ Resume từ index {start_idx} (checkpoint)")
        except ValueError:
            start_idx = 0

    # Upsert theo batch
    total = len(records)
    try:
        for i in range(start_idx, total, BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            texts = [r["text"] for r in batch]
            vectors = embed_batch(texts)

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
                    print(f"  ⚠ Upsert lỗi (lần {attempt}): {e} — thử lại sau {attempt*3}s")
                    time.sleep(attempt * 3)

            checkpoint_path.write_text(str(i + BATCH_SIZE))
            print(f"  ↑ {min(i + BATCH_SIZE, total)}/{total}")

    except Exception:
        print(f"\n⚠ Crash tại index ~{i}. Chạy lại để resume tự động.")
        raise

    checkpoint_path.unlink(missing_ok=True)
    print(f"\n🎉 Xong: {total} entries → collection '{COLLECTION}'")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nạp dictionary_v2.jsonl vào Qdrant collection edu_dictionary."
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
    parser.add_argument(
        "--vector-dim",
        type=int,
        default=int(os.getenv("VECTOR_DIM", "1024")),
        help="Vector dimension (default 1024 cho AITeamVN/Vietnamese_Embedding)",
    )
    args = parser.parse_args()

    ingest(dry_run=args.dry_run, recreate=args.recreate, vector_dim_hint=args.vector_dim)


if __name__ == "__main__":
    main()
