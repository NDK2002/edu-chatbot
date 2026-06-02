#!/usr/bin/env python3
"""
gen_dict_v2.py
==============
Tạo dictionary_v2.jsonl gồm 3 loại chunks:
  1. word_chunk   — community data (vi_tay_nung), 1 từ = 1 chunk, text 2 chiều
  2. topic_chunk  — community data gom theo chủ đề, 1 topic = 1 chunk
  3. word_chunk   — Lương Bèn (tay_vi), bỏ cross-ref (x.) và vi quá ngắn

Cách dùng:
    python -m backend.scripts.gen_dict_v2
    python -m backend.scripts.gen_dict_v2 --dry-run
"""

import argparse
import json
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT          = Path(__file__).resolve().parent.parent.parent
SRC_COMMUNITY = ROOT / "data" / "chunks" / "dict_vi_tay_nung.jsonl"
SRC_LUONG_BEN = ROOT / "data" / "chunks" / "luong_ben_parsed.jsonl"
OUTPUT        = ROOT / "data" / "chunks" / "dictionary_v2.jsonl"


def remove_diacritics(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def first_variant(raw: str) -> str:
    """Lấy biến thể đầu tiên từ chuỗi có nhiều variants."""
    if not raw:
        return ""
    for sep in ("(", "/", ";", "\n"):
        raw = raw.split(sep)[0]
    return raw.strip()


def variants_str(variants) -> str:
    if not variants:
        return ""
    if isinstance(variants, list):
        return " / ".join(v.strip() for v in variants if v.strip())
    return str(variants).strip()


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ── 1. Community word chunks ───────────────────────────────────────────────────

def make_community_word_chunks(records: list[dict]) -> list[dict]:
    chunks = []
    for r in records:
        vi    = (r.get("vi") or "").strip()
        tay   = variants_str(r.get("tay_variants"))
        nung  = variants_str(r.get("nung_variants"))
        topic = (r.get("topic") or "").strip()
        if not vi:
            continue

        tay_short  = first_variant(tay)
        nung_short = first_variant(nung)
        vi_nd      = remove_diacritics(vi)
        topic_nd   = remove_diacritics(topic) if topic else ""

        lines = [f"Tiếng Việt: {vi}"]
        if tay:
            lines.append(f"Tiếng Tày: {tay}")
        if nung:
            lines.append(f"Tiếng Nùng: {nung}")
        if topic:
            lines.append(f"Chủ đề: {topic}")

        # Reverse lookup hint — giúp embed capture chiều Tày→Việt
        reverse_parts = []
        if tay_short:
            reverse_parts.append(f"Tày: {tay_short}")
        if nung_short:
            reverse_parts.append(f"Nùng: {nung_short}")
        if reverse_parts:
            lines.append(f"({'; '.join(reverse_parts)} = {vi})")

        search_terms = " ".join(filter(None, [vi_nd, topic_nd]))
        text = "\n".join(lines) + f"\n[search: {search_terms}]"

        chunks.append({
            "content_type":      "word_chunk",
            "direction":         "vi_to_tay_nung",
            "vi":                vi,
            "vi_no_diacritics":  vi_nd,
            "tay":               tay,
            "nung":              nung,
            "topic":             topic,
            "topic_no_diacritics": topic_nd,
            "text":              text,
            "source":            r.get("source_file", "du_lieu_tu_dien_viet_tay_nung.pdf"),
            "review_status":     r.get("review_status", "community_source_need_review"),
            "quality_tier":      "community",
        })
    return chunks


# ── 2. Topic chunks ────────────────────────────────────────────────────────────

def make_topic_chunks(records: list[dict]) -> list[dict]:
    topics: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        t = (r.get("topic") or "").strip()
        if t:
            topics[t].append(r)

    chunks = []
    for topic, entries in sorted(topics.items()):
        rows     = []
        vi_terms = []

        for r in entries:
            vi   = (r.get("vi") or "").strip()
            tay  = variants_str(r.get("tay_variants"))
            nung = variants_str(r.get("nung_variants"))
            if not vi:
                continue

            parts = [vi]
            if tay:
                parts.append(f"Tày: {tay}")
            if nung:
                parts.append(f"Nùng: {nung}")
            rows.append(" — ".join(parts))
            vi_terms.append(remove_diacritics(vi))

        if not rows:
            continue

        content = f"Chủ đề: {topic.upper()}\n" + "\n".join(rows)
        search  = " ".join(vi_terms[:30])

        topic_nd = remove_diacritics(topic)
        chunks.append({
            "content_type":        "topic_chunk",
            "direction":           "vi_to_tay_nung",
            "topic":               topic,
            "topic_no_diacritics": topic_nd,
            "entry_count":         len(rows),
            "text":                content + f"\n[search: {topic_nd} {search}]",
            "source":              "du_lieu_tu_dien_viet_tay_nung.pdf",
            "review_status":       "community_source_need_review",
            "quality_tier":        "community",
        })
    return chunks


# ── 3. Lương Bèn word chunks ───────────────────────────────────────────────────

def make_luong_ben_word_chunks(records: list[dict]) -> tuple[list[dict], dict]:
    chunks = []
    stats  = {"total": 0, "skipped_xref": 0, "skipped_short": 0, "ok": 0}

    for r in records:
        stats["total"] += 1
        vi  = (r.get("vi") or "").strip()
        tay = (r.get("tay") or "").strip()

        if not vi or not tay:
            stats["skipped_short"] += 1
            continue

        # Bỏ cross-reference entries ("x. tên_entry_khác")
        if vi.startswith("x."):
            stats["skipped_xref"] += 1
            continue

        # Bỏ vi quá ngắn (1 ký tự — thường là lỗi parse)
        if len(vi) < 2:
            stats["skipped_short"] += 1
            continue

        vi_nd = remove_diacritics(vi)
        tay_v = first_variant(tay)

        # Reverse lookup hint ngắn gọn
        reverse = f"(Tày: {tay_v} = {vi})" if tay_v else ""

        lines = [
            f"Tiếng Việt: {vi}",
            f"Tiếng Tày: {tay}",
        ]
        if reverse:
            lines.append(reverse)

        text = "\n".join(lines) + f"\n[search: {vi_nd}]"

        chunks.append({
            "content_type":     "word_chunk",
            "direction":        "tay_to_vi",
            "vi":               vi,
            "vi_no_diacritics": vi_nd,
            "tay":              tay,
            "text":             text,
            "source":           r.get("source", "tu_dien_tay_viet_luong_ben"),
            "review_status":    r.get("review_status", "academic_source_trusted"),
            "quality_tier":     r.get("quality_tier", "high"),
        })
        stats["ok"] += 1

    return chunks, stats


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tạo dictionary_v2.jsonl với word + topic chunks"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Chỉ thống kê, không ghi file")
    args = parser.parse_args()

    print("📂 Đọc community data ...")
    community = load_jsonl(SRC_COMMUNITY)
    print(f"   {len(community)} entries")

    print("📂 Đọc Lương Bèn ...")
    luong_ben = load_jsonl(SRC_LUONG_BEN)
    print(f"   {len(luong_ben)} entries")

    print("\n🔄 Tạo chunks ...")
    word_chunks_comm  = make_community_word_chunks(community)
    topic_chunks      = make_topic_chunks(community)
    word_chunks_lb, lb_stats = make_luong_ben_word_chunks(luong_ben)

    all_chunks = word_chunks_comm + topic_chunks + word_chunks_lb

    print(f"\n📊 Kết quả:")
    print(f"   Community word chunks : {len(word_chunks_comm)}")
    print(f"   Topic chunks          : {len(topic_chunks)}  ({', '.join(c['topic'] for c in topic_chunks)})")
    print(f"   Lương Bèn word chunks : {len(word_chunks_lb)}")
    print(f"     skipped x-ref       : {lb_stats['skipped_xref']}")
    print(f"     skipped short/empty : {lb_stats['skipped_short']}")
    print(f"   TOTAL                 : {len(all_chunks)} chunks")

    if args.dry_run:
        print("\n🔍 Dry-run — sample mỗi loại:")
        print("\n[community word_chunk]")
        print(word_chunks_comm[0]["text"])
        print("\n[topic_chunk]")
        print(topic_chunks[0]["text"][:300])
        print("\n[luong_ben word_chunk]")
        print(word_chunks_lb[0]["text"])
        return

    with open(OUTPUT, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"\n✅ Ghi xong: {OUTPUT.name}")
    print(f"   {len(all_chunks)} chunks | {OUTPUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
