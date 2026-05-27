"""
Add Vietnamese no-accent keyword variants to a JSONL chunk file.

Example:
    python -m backend.scripts.add_no_accent_keywords --input data/chunks/theory_chunks.jsonl
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path


def remove_vietnamese_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "D")


def build_keyword_list(keywords: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for keyword in keywords:
        if not isinstance(keyword, str):
            continue

        cleaned = " ".join(keyword.split())
        if not cleaned:
            continue

        for variant in (cleaned, remove_vietnamese_accents(cleaned)):
            normalized_variant = variant.casefold()
            if not variant or normalized_variant in seen:
                continue
            seen.add(normalized_variant)
            result.append(variant)

    return result


def process_file(input_path: Path, output_path: Path) -> tuple[int, int]:
    total = 0
    updated = 0

    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8", newline="\n") as dst:
        for line in src:
            total += 1
            record = json.loads(line)
            original_keywords = record.get("keywords")

            if isinstance(original_keywords, list):
                new_keywords = build_keyword_list(original_keywords)
                if new_keywords != original_keywords:
                    record["keywords"] = new_keywords
                    updated += 1

            dst.write(json.dumps(record, ensure_ascii=False) + "\n")

    return total, updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input JSONL file path")
    parser.add_argument(
        "--output",
        help="Optional output JSONL path. Defaults to overwrite input file in-place.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(input_path.suffix + ".tmp")

    total, updated = process_file(input_path, output_path)

    if not args.output:
        output_path.replace(input_path)

    print(f"Processed {total} records")
    print(f"Updated {updated} records")
    print(f"Output: {args.output or input_path}")


if __name__ == "__main__":
    main()
