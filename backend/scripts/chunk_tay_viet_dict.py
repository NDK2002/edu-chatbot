"""
chunk_tay_viet_dict.py
Parse Từ điển Tày–Việt (Lương Bèn, NXB ĐH Thái Nguyên 2011) from PDF
into one JSONL chunk per dictionary entry.

Strategy:
- PDF has 2-column layout; columns are split at x ≈ 210 on a 411-wide page
- Headwords are in Times New Roman Bold 12pt
- Subscript homograph numbers are small (size ≤ 8pt), bold or not
- Definition text is Regular or Italic 12pt
- Section headers are Bold ≥ 14pt (Calibri Bold 18pt or TNR Bold 40pt) → skip
- Page headers/footers (top < 55 or top > 538) → skip

Output JSONL schema (matches Qdrant collection `edu_tay_vi_dictionary`):
{
  "domain": "dictionary",
  "direction": "tay_to_vi",
  "tay": "ải chải",
  "tay_subscript": null,
  "vi": "cật lực. Hết ~: làm cật lực.",
  "source_file": "Từ điển Tày–Việt Lương Bèn",
  "review_status": "dictionary_source"
}

Usage:
    pip install pdfplumber --break-system-packages
    python scripts/chunk_tay_viet_dict.py \\
        --pdf path/to/tu_dien_tay_viet.pdf \\
        --out data/chunks/tay_viet_dict.jsonl
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("Install pdfplumber:  pip install pdfplumber --break-system-packages")

# ── constants ─────────────────────────────────────────────────────────────────
COL_SPLIT_X      = 210   # left: x0 < 210, right: x0 >= 210
PAGE_TOP_MIN     = 55    # drop page-header rows
PAGE_TOP_MAX     = 538   # drop page-footer / page-number rows (~542)
FIRST_DICT_PAGE  = 16    # 0-indexed; physical page 17 = first real entries
# Section letters appear at 18pt (Calibri Bold) or 40pt (TNR Bold) — filter both
SECTION_MIN_SIZE = 14    # bold chars with size >= this are section headers, not headwords
LINE_TOLERANCE   = 4     # px: chars within this delta of top → same line
BOLD_RE          = re.compile(r"Bold", re.I)


# ── helpers ───────────────────────────────────────────────────────────────────

def is_bold(char: dict) -> bool:
    return bool(BOLD_RE.search(char.get("fontname", "")))


def char_col(char: dict) -> str:
    return "L" if char["x0"] < COL_SPLIT_X else "R"


def group_lines(chars: list) -> list:
    if not chars:
        return []
    chars = sorted(chars, key=lambda c: (c["top"], c["x0"]))
    lines = []
    cur = [chars[0]]
    for c in chars[1:]:
        if abs(c["top"] - cur[-1]["top"]) <= LINE_TOLERANCE:
            cur.append(c)
        else:
            lines.append(cur)
            cur = [c]
    lines.append(cur)
    return lines


def line_to_text(chars: list) -> str:
    if not chars:
        return ""
    chars = sorted(chars, key=lambda c: c["x0"])
    text = chars[0]["text"]
    for prev, cur in zip(chars, chars[1:]):
        if cur["x0"] - prev["x1"] > 2:
            text += " "
        text += cur["text"]
    return text.strip()


# ── column parser ─────────────────────────────────────────────────────────────

def parse_column(col_chars: list) -> list:
    """Return list of {"tay", "tay_subscript", "vi"} dicts from one column."""
    lines = group_lines(col_chars)
    entries = []
    current_hw = None
    current_sub = None
    current_def = []

    def flush():
        nonlocal current_hw, current_sub, current_def
        if current_hw is None:
            return
        vi = re.sub(r" {2,}", " ", " ".join(current_def)).strip()
        if vi:
            entries.append({"tay": current_hw, "tay_subscript": current_sub, "vi": vi})
        current_hw = None
        current_sub = None
        current_def = []

    for line_chars in lines:
        # Subscripts: size ≤ 8, bold or not
        sub_chars  = [c for c in line_chars if round(c["size"]) <= 8]
        # Headword chars: bold, 8 < size < SECTION_MIN_SIZE
        hw_chars   = [c for c in line_chars
                      if is_bold(c) and 8 < round(c["size"]) < SECTION_MIN_SIZE]
        # Definition chars: non-bold, normal size
        norm_chars = [c for c in line_chars
                      if not is_bold(c) and round(c["size"]) > 8]

        hw_text   = line_to_text(hw_chars).strip()
        sub_text  = line_to_text(sub_chars).strip()
        norm_text = line_to_text(norm_chars).strip()

        if hw_text:
            flush()
            current_hw  = re.sub(r" {2,}", " ", hw_text)
            current_sub = int(sub_text) if sub_text.isdigit() else None
            if norm_text:
                current_def.append(norm_text)
        elif sub_text.isdigit() and current_hw is not None:
            if current_sub is None:
                current_sub = int(sub_text)
        else:
            if norm_text and current_hw is not None:
                current_def.append(norm_text)

    flush()
    return entries


# ── page processor ────────────────────────────────────────────────────────────

def process_page(page) -> list:
    chars = page.chars
    # Drop header/footer band
    chars = [c for c in chars if PAGE_TOP_MIN < c["top"] < PAGE_TOP_MAX]
    # Drop section-header letters (large bold regardless of font)
    chars = [c for c in chars
             if not (is_bold(c) and round(c["size"]) >= SECTION_MIN_SIZE)]

    left  = [c for c in chars if char_col(c) == "L"]
    right = [c for c in chars if char_col(c) == "R"]
    return parse_column(left) + parse_column(right)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Chunk Tày-Việt dictionary PDF → JSONL (one line per entry)")
    parser.add_argument("--pdf",  required=True, help="Path to tu_dien_tay_viet.pdf")
    parser.add_argument("--out",  default="data/chunks/tay_viet_dict.jsonl")
    parser.add_argument("--start-page", type=int, default=FIRST_DICT_PAGE,
                        help="0-indexed first page (default 16 = page 17)")
    parser.add_argument("--end-page", type=int, default=None,
                        help="0-indexed last page inclusive (default: last)")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    TEMPLATE = {
        "domain": "dictionary",
        "direction": "tay_to_vi",
        "source_file": "Từ điển Tày–Việt Lương Bèn",
        "review_status": "dictionary_source",
    }

    total = 0
    with pdfplumber.open(args.pdf) as pdf:
        end = args.end_page if args.end_page is not None else len(pdf.pages) - 1
        pages = pdf.pages[args.start_page: end + 1]
        print(f"Processing {len(pages)} pages ({args.start_page+1}–{end+1})…",
              flush=True)

        with out_path.open("w", encoding="utf-8") as fout:
            for page_idx, page in enumerate(pages, start=args.start_page):
                try:
                    entries = process_page(page)
                except Exception as exc:
                    print(f"  ⚠ page {page_idx+1}: {exc}", file=sys.stderr, flush=True)
                    continue

                for e in entries:
                    row = dict(TEMPLATE)
                    row["tay"] = e["tay"]
                    if e["tay_subscript"] is not None:
                        row["tay_subscript"] = e["tay_subscript"]
                    row["vi"] = e["vi"]
                    fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                    total += 1

    print(f"Done. {total} entries written to {out_path}", flush=True)


if __name__ == "__main__":
    main()
