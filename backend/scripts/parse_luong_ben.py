#!/usr/bin/env python3
"""
parse_luong_ben.py
==================
Parse file Marker markdown của Từ điển Tày–Việt (Lương Bèn)
→ JSONL theo schema của dictionary_combined.jsonl

Input:  data/raw/datalab-output-tu_dien_tay_viet.pdf.md
Output: data/chunks/luong_ben_parsed.jsonl

Cách dùng:
    python -m backend.scripts.parse_luong_ben
    python -m backend.scripts.parse_luong_ben --dry-run   # in 20 entries đầu, không ghi file
    python -m backend.scripts.parse_luong_ben --stats     # chỉ in thống kê
"""

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_MD  = ROOT / "data" / "raw" / "datalab-output-tu_dien_tay_viet.pdf.md"
OUTPUT_JSONL = ROOT / "data" / "chunks" / "luong_ben_parsed.jsonl"

SOURCE     = "tu_dien_tay_viet_luong_ben"
SOURCE_TYPE = "academic_dictionary"
DIALECT    = "Tày (chuẩn)"
DIRECTION  = "tay_vi"
REVIEW_STATUS = "academic_source_trusted"

# ── Bảng sửa lỗi ư→u hệ thống từ Marker OCR ─────────────────────────────────
# Marker đọc font PDF bị lỗi: ư → u trong nhiều vị trí
# Xây dựng từ so sánh với blog Tày Lạng Sơn + kiến thức ngôn ngữ
# Format: (pattern_regex, replacement)  — áp trên toàn bộ definition text
OCR_REPLACEMENTS = [
    # Các cụm cố định bị sai ư→u
    (r'\bhẩu\b',       'hẩư'),   # hẩư = đưa cho
    (r'\bháu\b',       'háư'),   # háư = còn lại / chờ
    (r'\bpây\b',       'pây'),   # đúng rồi (giữ nguyên)
    (r'\bchứu\b',      'chứư'),  # chứư = chữa
    (r'\blườn\b',      'lườn'),  # đúng rồi
    (r'\brưòn\b',      'rườn'),  # sai: rươn bị đảo dấu
    (r'\brươn\b',      'rườn'),
    (r'\bslưa\b',      'slưa'),  # đúng rồi
    (r'\bkhửu\b',      'khửu'),  # đúng rồi
    (r'\bthâu\b',      'thâu'),  # đúng (có thể là thâu hoặc thâư)
    (r'\bchâu thờ\b',  'châư thở'),  # Au châư thở
    (r'\bchâu\b(?=\s+thờ)', 'châư'),
    # Dấu ờ → ở
    (r'\bthờ\b',       'thở'),   # thở (breathe)
    # Các từ phổ biến bị lỗi thanh điệu
    (r'\bbầu\b(?=\s+lập)',  'bấu'),   # bấu lập = không kịp
    (r'\bbầu\b(?=\s+đảy)', 'bấu'),   # bấu đảy = không được
    (r'\bbầu\b(?=\s+mì)',  'bấu'),   # bấu mì = không có
    (r'\bbầu\b(?=\s+pây)', 'bấu'),   # bấu pây = không đi
    (r'\bbầu\b(?=\s+kin)', 'bấu'),   # bấu kin = không ăn
    (r'\bbầu\b(?=\s+oóc)', 'bấu'),   # bấu oóc = không ra
    (r'\bmẹn\b',       'mền'),   # mền = nên (trong context "tầu lồm đảng mền ay")
    (r'\btầu\b',       'tầư'),   # tầư = bị (passive marker)
    (r'\blôm\b',       'lồm'),   # lồm = gió
    (r'\bđãng\b',      'đảng'),  # đảng = lạnh
]

# Compile patterns
_OCR_PATTERNS = [(re.compile(p), r) for p, r in OCR_REPLACEMENTS]


def apply_ocr_fixes(text: str) -> str:
    """Áp các corrections OCR đã biết."""
    for pattern, replacement in _OCR_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def remove_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt để làm vi_no_diacritics."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower()


def clean_headword(raw: str) -> str:
    """
    Xử lý headword từ markdown bold.
    - Bỏ <sub>N</sub>
    - Normalize whitespace
    - Giữ nguyên case (Tày dùng chữ thường/hoa có nghĩa)
    """
    # Bỏ subscript tag
    hw = re.sub(r'<sub>\d+</sub>', '', raw)
    # Bỏ ký tự markdown còn sót
    hw = hw.replace('**', '').strip()
    # Normalize whitespace
    hw = re.sub(r'\s+', ' ', hw)
    return hw


def extract_homonym_index(raw: str) -> int | None:
    """Trích số thứ tự đồng âm từ <sub>N</sub>. Trả None nếu không có."""
    m = re.search(r'<sub>(\d+)</sub>', raw)
    return int(m.group(1)) if m else None


def quality_tier(definition: str) -> str:
    """
    Phân loại quality dựa trên độ phong phú định nghĩa.
    Giống logic của file gốc.
    """
    stripped = definition.strip()
    if '*' in stripped and '~' in stripped:
        return 'high'
    if len(stripped) > 60:
        return 'medium'
    return 'low'


def extract_vi_meaning(definition: str) -> str:
    """
    Trích nghĩa tiếng Việt chính từ definition string.

    Nguyên tắc: nghĩa tiếng Việt luôn đứng TRƯỚC ví dụ.
    Ví dụ bắt đầu bằng '*' (italic tày) hoặc '~' (placeholder đầu từ).
    Nên cắt text tại vị trí đầu tiên của '*' hoặc khoảng trắng+'~'.

    Cấu trúc:
        "1. nghĩa. *ví dụ tày* ~: dịch. 2. nghĩa2."
        "*ngữ cảnh* nghĩa. *ví dụ*: dịch."
    """
    text = definition.strip()

    # Bước 1: bỏ \* (escaped asterisk — dấu tục ngữ/proverb marker trong PDF)
    text = re.sub(r'\\\*', '', text)

    # Bước 2: bỏ italic block MỞ ĐẦU (ngữ cảnh tổ hợp như "*rối*", "*dề*", "*lùa*")
    text = re.sub(r'^\*[^*]+\*\s*', '', text)

    # Bước 3: bỏ đánh số đầu "1. " hoặc "1) "
    text = re.sub(r'^\d+[.)]\s*', '', text)

    # Bước 4: tìm vị trí bắt đầu ví dụ — dấu '*' đầu tiên hoặc khoảng trắng trước '~'
    cut = len(text)
    m_star = re.search(r'\*', text)
    if m_star:
        cut = min(cut, m_star.start())
    m_tilde = re.search(r'\s~', text)
    if m_tilde:
        cut = min(cut, m_tilde.start())

    meaning = text[:cut].strip().rstrip(' .,;!?')

    # Bước 5: nếu đa nghĩa ("1. X. 2. Y."), lấy nghĩa đầu tiên
    parts = re.split(r'\s+\d+\.\s+', meaning)
    meaning = parts[0].strip().rstrip(' .,;!?')

    return meaning


def make_text(tay: str, vi: str) -> str:
    """Tạo field text cho embedding."""
    vi_nd = remove_diacritics(vi)
    return f"{tay} — {vi}\n[search: {vi_nd}]"


def make_id(tay: str, vi: str, idx: int | None) -> int:
    key = f"tay_vi|{tay.lower()}|{vi.lower()}|{idx or 0}"
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)
    return h % (2**53)


# ── Parser chính ──────────────────────────────────────────────────────────────

ENTRY_RE = re.compile(
    r'^\*\*(.+?)\*\*\s+(.*)',   # **headword** rest_of_line
    re.DOTALL
)

SECTION_RE = re.compile(r'^#{1,3}\s+([A-ZĂÂĐÊƠƯ][\w\s]*)$')


def parse_markdown(md_path: Path) -> list[dict]:
    with open(md_path, encoding='utf-8') as f:
        raw = f.read()

    # Cắt phần từ điển: từ "### A" đến "### Sli" (phần thơ ca)
    dict_start = raw.find('\n### A\n')
    dict_end   = raw.find('\n### Sli')
    if dict_start == -1:
        raise ValueError("Không tìm thấy section ### A trong file")
    if dict_end == -1:
        dict_end = len(raw)

    dict_text = raw[dict_start:dict_end]

    # Nối các dòng bị cắt giữa chừng (continuation lines)
    # Dòng continuation: không bắt đầu bằng ** hay # hay empty, và dòng trước kết thúc bằng "  "
    lines = dict_text.split('\n')
    merged_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Nếu dòng hiện tại kết thúc bằng trailing spaces (line break) và dòng sau
        # là continuation (không phải entry mới, không phải heading, không rỗng)
        if line.endswith('  ') and i + 1 < len(lines):
            next_line = lines[i + 1]
            is_new_entry = next_line.startswith('**') or next_line.startswith('#') or not next_line.strip()
            if not is_new_entry and next_line.strip():
                # Merge: bỏ trailing spaces, nối với next
                merged_lines.append(line.rstrip() + ' ' + next_line.strip())
                i += 2
                continue
        merged_lines.append(line)
        i += 1

    records = []
    current_section = 'A'

    for line in merged_lines:
        line = line.strip()
        if not line:
            continue

        # Section header
        sec_m = SECTION_RE.match(line)
        if sec_m:
            current_section = sec_m.group(1).strip()
            continue

        # Entry line: bắt đầu bằng **
        entry_m = ENTRY_RE.match(line)
        if not entry_m:
            continue

        raw_headword = entry_m.group(1)
        definition   = entry_m.group(2).strip()

        if not definition:
            continue

        # Xử lý headword
        homonym_idx = extract_homonym_index(raw_headword)
        tay = clean_headword(raw_headword)

        if not tay:
            continue

        # Lấy nghĩa tiếng Việt chính (dùng hàm extract_vi_meaning)
        vi_first = extract_vi_meaning(definition)

        if not vi_first or len(vi_first) < 1:
            continue

        # Áp OCR corrections
        definition_fixed = apply_ocr_fixes(definition)
        vi_first_fixed   = apply_ocr_fixes(vi_first)

        # Build record
        vi_no_diacritics = remove_diacritics(vi_first_fixed)
        text = make_text(tay, vi_first_fixed)

        record = {
            "source":          SOURCE,
            "source_type":     SOURCE_TYPE,
            "direction":       DIRECTION,
            "dialect":         DIALECT,
            "language":        "vi-tay",
            "content_type":    "dictionary_entry",
            "tay":             tay,
            "vi":              vi_first_fixed,
            "vi_no_diacritics": vi_no_diacritics,
            "definition_full": apply_ocr_fixes(definition),
            "text":            text,
            "review_status":   REVIEW_STATUS,
            "quality_tier":    quality_tier(definition),
            "source_id":       1,
        }

        if homonym_idx is not None:
            record["homonym_index"] = homonym_idx

        if current_section:
            record["section"] = current_section

        records.append(record)

    return records


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Parse Marker markdown của Từ điển Tày–Việt → JSONL"
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='In 20 entries đầu, không ghi file')
    parser.add_argument('--stats', action='store_true',
                        help='Chỉ in thống kê')
    parser.add_argument('--input', type=Path, default=INPUT_MD,
                        help=f'File markdown input (mặc định: {INPUT_MD})')
    parser.add_argument('--output', type=Path, default=OUTPUT_JSONL,
                        help=f'File JSONL output (mặc định: {OUTPUT_JSONL})')
    args = parser.parse_args()

    if not args.input.exists():
        print(f"⛔ Không tìm thấy: {args.input}")
        return

    print(f"📂 Đọc: {args.input.name}")
    records = parse_markdown(args.input)
    print(f"   → {len(records)} entries parsed")

    # Thống kê
    sections = {}
    tiers = {}
    for r in records:
        s = r.get('section', '?')
        sections[s] = sections.get(s, 0) + 1
        t = r.get('quality_tier', '?')
        tiers[t] = tiers.get(t, 0) + 1

    print(f"\n📊 Thống kê:")
    print(f"   Quality: {tiers}")
    print(f"   Sections: {len(sections)} vần ({', '.join(sorted(sections.keys())[:8])}...)")

    if args.dry_run:
        print(f"\n🔍 Dry-run — 20 entries đầu:")
        for r in records[:20]:
            print(f"   [{r.get('section','')}] {r['tay']!r:25s} → {r['vi']!r}")
        return

    if args.stats:
        return

    # Ghi JSONL
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f"\n✅ Ghi xong: {args.output}")
    print(f"   {len(records)} entries | {args.output.stat().st_size:,} bytes")


if __name__ == '__main__':
    main()
