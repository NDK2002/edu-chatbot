#!/usr/bin/env python3
"""
parse_dict.py
=============
Parse 2 từ điển PDF → JSONL cho Qdrant.

Cách dùng:
    python -m backend.scripts.parse_dict

Output:
    data/chunks/dict_vi_tay_nung.jsonl   — Việt → Tày/Nùng
    data/chunks/dict_tay_vi.jsonl        — Tày  → Việt
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "data" / "raw"
CHUNKS_DIR = ROOT / "data" / "chunks"
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

VI_TAY_NUNG_PDF = RAW_DIR / "du_lieu_tu_dien_viet_tay_nung.pdf"
TAY_VI_PDF = RAW_DIR / "tu_dien_tay_viet.pdf"
VI_TAY_NUNG_JSONL = CHUNKS_DIR / "dict_vi_tay_nung.jsonl"
TAY_VI_JSONL = CHUNKS_DIR / "dict_tay_vi.jsonl"


# ── Shared utilities ──────────────────────────────────────────────────────────

def remove_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt/Tày, trả về ASCII lowercase."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()


def nfc(text: str) -> str:
    # Chuẩn hóa NFC + bỏ ký tự vùng PUA (Private Use Area) thường xuất hiện trong PDF
    text = re.sub(r"[-]", "", text)
    return unicodedata.normalize("NFC", text).strip()


def words_to_rows(
    words: list[dict],
    header_cutoff: float = 90.0,
    y_tol: float = 4.0,
) -> list[list[dict]]:
    """
    Group pdfplumber word dicts vào các dòng trực quan.
    Bỏ qua phần header trang (top <= header_cutoff).
    """
    data = [w for w in words if w["top"] > header_cutoff]
    rows: list[list[dict]] = []
    cur: list[dict] = []
    prev_top: float | None = None
    for w in sorted(data, key=lambda w: (w["top"], w["x0"])):
        if prev_top is None or abs(w["top"] - prev_top) <= y_tol:
            cur.append(w)
            if prev_top is None:
                prev_top = w["top"]
        else:
            rows.append(cur)
            cur = [w]
            prev_top = w["top"]
    if cur:
        rows.append(cur)
    return rows


# ── Parser 1: Việt → Tày/Nùng ────────────────────────────────────────────────
#
# Cấu trúc PDF: bảng 5 cột (đo bằng pt)
#   STT   | VIỆT     | TÀY      | NÙNG      | GHI CHÚ
#   x<88  | 88–189   | 189–322  | 322–492   | x>=492
#
# Header trang: 3 dòng đầu (top<=90) — bỏ qua.
# Mỗi entry mới: cột STT có số nguyên.

_STT_MAX = 88.0
_VIET_MAX = 189.0
_TAY_MAX = 322.0
_NUNG_MAX = 492.0

_FALLBACK_TOPICS: dict[int, str] = {
    1: "cơ thể người",
    99: "xưng hô",
    162: "đồ gia dụng",
    265: "động vật",
    395: "thực vật",
}


def _load_topic_ranges(page1_text: str) -> dict[int, str]:
    """Đọc bảng mục lục chủ đề từ trang 1."""
    topics = dict(_FALLBACK_TOPICS)
    for m in re.finditer(r"Từ dòng\s+(\d+)\s*:\s*(.+)", page1_text):
        stt = int(m.group(1))
        raw = m.group(2).strip()
        # Bỏ tiền tố "tên các / các từ / các / từ"
        topic = re.sub(r"(?i)^(tên các |các từ |các |từ )", "", raw).strip().lower()
        # Chỉ lấy cụm danh từ chính
        topic = re.split(r" trong | ngoài | liên | thuộc ", topic)[0].strip()
        topics[stt] = topic
    return topics


def _topic_for(stt: int, ranges: dict[int, str]) -> str:
    result = "chung"
    for start in sorted(ranges):
        if stt >= start:
            result = ranges[start]
    return result


def _split_variants(raw: str) -> list[str]:
    """
    Tách text cột Tày/Nùng thành list biến thể.
    Ưu tiên split theo `;`.
    Nếu không có `;`, tách theo pattern `) word` (sau ngoặc đóng xuất hiện từ mới).
    """
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return []

    # Ưu tiên split theo ; (nhiều entry dùng dấu chấm phẩy)
    if ";" in raw:
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        # Mỗi part có thể vẫn chứa nhiều biến thể → đệ quy
        result = []
        for p in parts:
            result.extend(_split_variants_by_paren(p))
        return result

    return _split_variants_by_paren(raw)


def _split_variants_by_paren(raw: str) -> list[str]:
    """
    Tách chuỗi thành các biến thể theo pattern `) word`.
    Ví dụ: "thua (hòa an - CB) hua (Cao Lộc)" → ["thua (hòa an - CB)", "hua (Cao Lộc)"]
    """
    raw = raw.strip()
    if not raw:
        return []
    # Chỉ split khi có ít nhất 1 ngoặc đóng theo sau là khoảng trắng + ký tự chữ
    if ")" not in raw:
        return [raw]
    parts = re.split(r"\)\s+(?=[A-Za-zÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐàáảãạăằắẳẵặâầấẩẫậđ])", raw)
    if len(parts) == 1:
        return [raw]
    result = []
    for i, p in enumerate(parts):
        p = p.strip()
        if not p:
            continue
        # Thêm lại `)` cho tất cả phần trừ phần cuối (đã consume `)` khi split)
        result.append(p + ")" if i < len(parts) - 1 else p)
    return result


def parse_vi_tay_nung() -> list[dict]:
    """Parse du_lieu_tu_dien_viet_tay_nung.pdf."""
    entries: dict[int, dict] = {}
    topics: dict[int, str] = {}

    with pdfplumber.open(VI_TAY_NUNG_PDF) as pdf:
        topics = _load_topic_ranges(pdf.pages[0].extract_text() or "")

        for page_idx, page in enumerate(pdf.pages):
            words = page.extract_words(keep_blank_chars=False)
            if not words:
                continue
            rows = words_to_rows(words, header_cutoff=90.0)

            current_stt: int | None = None

            for row in rows:
                # Phát hiện STT mới (số nguyên trong cột trái)
                stt_tok = " ".join(
                    w["text"] for w in row if w["x0"] < _STT_MAX
                ).strip()
                if re.fullmatch(r"\d{1,4}", stt_tok):
                    current_stt = int(stt_tok)
                    entries.setdefault(
                        current_stt,
                        {
                            "stt": current_stt,
                            "vi": "",
                            "tay": "",
                            "nung": "",
                            "note": "",
                            "page": page_idx + 1,
                        },
                    )

                if current_stt is None:
                    continue

                e = entries[current_stt]

                def seg(lo: float, hi: float) -> str:
                    return " ".join(
                        w["text"] for w in row if lo <= w["x0"] < hi
                    )

                for key, lo, hi in [
                    ("vi",   _STT_MAX,  _VIET_MAX),
                    ("tay",  _VIET_MAX, _TAY_MAX),
                    ("nung", _TAY_MAX,  _NUNG_MAX),
                    ("note", _NUNG_MAX, 9999.0),
                ]:
                    chunk = seg(lo, hi)
                    if chunk:
                        e[key] = (e[key] + " " + chunk).strip()

    records = []
    for stt in sorted(entries):
        e = entries[stt]
        vi = nfc(e["vi"])
        if not vi:
            continue

        tay_v = _split_variants(e["tay"])
        nung_v = _split_variants(e["nung"])

        # Xây text cho embedding
        parts = [f"{vi} (tiếng Việt):"]
        if tay_v:
            parts.append("tiếng Tày có thể là " + ", ".join(tay_v))
        if nung_v:
            parts.append("tiếng Nùng có thể là " + ", ".join(nung_v))
        text = "; ".join(parts) + "."

        records.append({
            "id": f"vi_tay_nung_{stt:05d}",
            "text": text,
            "vi": vi,
            "vi_no_accent": remove_accents(vi),
            "tay_variants": tay_v,
            "nung_variants": nung_v,
            "topic": _topic_for(stt, topics),
            "note": nfc(e["note"]) if e["note"] else "",
            "domain": "dictionary",
            "direction": "vi_to_tay_nung",
            "source_file": "du_lieu_tu_dien_viet_tay_nung.pdf",
            "source_page": e["page"],
            "review_status": "community_source_need_review",
        })

    return records


# ── Parser 2: Tày → Việt ─────────────────────────────────────────────────────
#
# Cấu trúc PDF: từ điển 1 cột, ~396 trang.
#   - Header trang: guide words (2 từ ngắn ở đầu trang, top<65) — bỏ qua.
#   - Entry mới: dòng bắt đầu bằng chữ HOA (^[A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐ])
#   - Continuation: dòng bắt đầu bằng chữ thường hoặc số
#   - Tách headword: mọi thứ trước "1. " hoặc "x. "
#   - ~ = ký hiệu thay thế headword trong ví dụ
#   - x. = xem → bỏ qua entry này

_SECTION_RE = re.compile(r"^[AĂÂBCDĐEÊGHIKLMNOÔƠPQRSTUƯVY]{1,2}$")
_HEADWORD_RE = re.compile(r"^[A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐ]")
_CROSS_REF_RE = re.compile(r"^x\.\s+")


def _split_headword(line: str) -> tuple[str, str]:
    """Tách (headword, phần_còn_lại) từ một dòng entry."""
    # "WORD 1. ..." → headword = WORD
    m = re.match(r"^(\S+)\s+(\d+\.\s+.+)", line)
    if m:
        return m.group(1), m.group(2)
    # "WORD x. ..."
    m = re.match(r"^(\S+)\s+(x\.\s+.+)", line)
    if m:
        return m.group(1), m.group(2)
    # "WORD rest"
    parts = line.split(None, 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (line, "")


def _extract_meanings(text: str) -> list[str]:
    """
    Trích nghĩa tiếng Việt từ văn bản entry.
    Không expand ~ (dùng ~ làm dấu phân tách).
    """
    # Thử tách theo số thứ tự nghĩa: "1. meaning. 2. meaning ..."
    parts = re.split(r"\s+\d+\.\s+", " " + text)
    if len(parts) > 1:
        meanings = []
        for p in parts[1:]:
            p = p.strip()
            # Nghĩa kết thúc trước ~, :, hoặc ". " (period + space)
            core = re.split(r"~|:|\.\s+", p)[0].strip().rstrip(". ")
            # Tách thêm theo dấu phẩy (nhiều từ đồng nghĩa)
            for sub in [s.strip() for s in core.split(",") if s.strip()]:
                meanings.append(sub)
        return meanings[:8]

    # Nghĩa duy nhất: lấy trước ~ hoặc : hoặc ". "
    core = re.split(r"~|:|\.\s+", text)[0].strip().rstrip(". ")
    meanings = [s.strip() for s in core.split(",") if s.strip()]
    return meanings[:8]


def _extract_examples(text: str, hw: str) -> list[str]:
    """
    Trích ví dụ dạng 'cụm_Tày: nghĩa_Việt'.
    Expand ~ → headword.
    """
    expanded = text.replace("~", hw.lower())
    examples = []
    # Tìm pattern: "headword word*: vi_meaning"
    hw_lower = re.escape(hw.lower())
    pat = re.compile(
        hw_lower + r"(?:\s+\S+){0,4}:\s*[\wàáảãạăằắẳẵặâầấẩẫậ][^.;]{3,40}",
        re.IGNORECASE,
    )
    for m in pat.finditer(expanded):
        examples.append(m.group(0).strip())
    return examples[:4]


def parse_tay_vi() -> list[dict]:
    """Parse tu_dien_tay_viet.pdf."""
    records: list[dict] = []
    idx = 0

    with pdfplumber.open(TAY_VI_PDF) as pdf:
        current_hw: str | None = None
        current_lines: list[str] = []
        current_page: int = 0

        def flush() -> None:
            nonlocal idx
            if not current_hw or not current_lines:
                return
            full = " ".join(current_lines).strip()
            if _CROSS_REF_RE.match(full):
                return

            meanings = _extract_meanings(full)
            examples = _extract_examples(full, current_hw)
            if not meanings:
                return

            text = f"{current_hw} (tiếng Tày): {', '.join(meanings[:4])}."
            if examples:
                text += " Ví dụ: " + "; ".join(examples[:2]) + "."

            records.append({
                "id": f"tay_vi_{idx:05d}",
                "text": text,
                "tay": nfc(current_hw),
                "tay_norm": nfc(current_hw).lower(),
                "tay_no_accent": remove_accents(current_hw),
                "vi_meanings": meanings,
                "examples": examples,
                "domain": "dictionary",
                "direction": "tay_to_vi",
                "source_file": "tu_dien_tay_viet.pdf",
                "source_page": current_page,
                "review_status": "dictionary_source",
            })
            idx += 1

        for page_idx, page in enumerate(pdf.pages):
            # Bỏ qua 16 trang đầu (trang bìa, lời tựa, mục lục)
            # Nội dung từ điển thực sự bắt đầu từ trang 17 (index 16)
            if page_idx < 16:
                continue
            words = page.extract_words(keep_blank_chars=False)
            if not words:
                continue
            # header_cutoff=65: bỏ guide words đầu trang (~top<65)
            rows = words_to_rows(words, header_cutoff=65.0)

            for row in rows:
                line = nfc(" ".join(w["text"] for w in row))
                if not line:
                    continue
                # Bỏ header chữ cái phần (A, Ă, Â ...) và dòng chỉ là số
                if _SECTION_RE.match(line) or re.fullmatch(r"\d+", line):
                    continue
                # Entry mới: dòng bắt đầu bằng chữ HOA
                if _HEADWORD_RE.match(line):
                    flush()
                    current_hw, rest = _split_headword(line)
                    current_lines = [rest] if rest else []
                    current_page = page_idx + 1
                else:
                    if current_hw:
                        current_lines.append(line)

        flush()  # Entry cuối cùng

    return records


# ── Main ──────────────────────────────────────────────────────────────────────

def _print_sample(records: list[dict], n: int = 3) -> None:
    for r in records[:n]:
        if r["direction"] == "vi_to_tay_nung":
            print(f"    {r['id']}: {r['vi']!r}")
            print(f"      tay={r['tay_variants'][:3]}")
            print(f"      nung={r['nung_variants'][:3]}")
        else:
            print(f"    {r['id']}: {r['tay']!r} → {r['vi_meanings'][:4]}")


def main() -> None:
    print("=" * 60)
    print("📖 Parsing Việt–Tày/Nùng dictionary...")

    vi_records = parse_vi_tay_nung()

    if len(vi_records) < 100:
        print(
            f"⛔ STOP: chỉ parse được {len(vi_records)} mục từ file 1"
            " (yêu cầu >= 100). Kiểm tra lại cấu trúc PDF."
        )
        sys.exit(1)

    with open(VI_TAY_NUNG_JSONL, "w", encoding="utf-8") as f:
        for rec in vi_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    no_tay = sum(1 for r in vi_records if not r["tay_variants"])
    no_nung = sum(1 for r in vi_records if not r["nung_variants"])
    print(f"  ✅ {len(vi_records)} mục → {VI_TAY_NUNG_JSONL.name}")
    print(f"  ⚠  {no_tay} mục không có từ Tày | {no_nung} mục không có từ Nùng")
    print("  📝 Mẫu 3 dòng đầu:")
    _print_sample(vi_records)

    print()
    print("📖 Parsing Tày–Việt dictionary (Lương Bèn)...")

    tay_records = parse_tay_vi()

    if len(tay_records) < 500:
        print(
            f"⛔ STOP: chỉ parse được {len(tay_records)} mục từ file 2"
            " (yêu cầu >= 500). Kiểm tra lại cấu trúc PDF."
        )
        sys.exit(1)

    with open(TAY_VI_JSONL, "w", encoding="utf-8") as f:
        for rec in tay_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"  ✅ {len(tay_records)} mục → {TAY_VI_JSONL.name}")
    print("  📝 Mẫu 3 dòng đầu:")
    _print_sample(tay_records)

    print()
    print("✅ Xong! Files đã lưu:")
    print(f"  {VI_TAY_NUNG_JSONL}")
    print(f"  {TAY_VI_JSONL}")


if __name__ == "__main__":
    main()
