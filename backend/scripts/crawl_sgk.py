"""
crawl_sgk.py
============
Crawl nội dung SGK Toán + Tiếng Việt lớp 1–9 từ loigiaihay.com
Lưu dạng JSON chunks sẵn để embed vào Qdrant.

Cách dùng:
    pip install requests beautifulsoup4 tqdm
    python crawl_sgk.py --grades 3 4 5 --subjects toan tieng-viet
    python crawl_sgk.py --all          # Crawl toàn bộ lớp 1-9

Output:
    data/sgk_chunks.jsonl  — mỗi dòng là 1 chunk JSON:
    {
        "id": "toan3-kntt-p16-c1",
        "title": "Toán lớp 3 trang 16 - Bảng nhân 3, bảng chia 3",
        "content": "...",
        "subject": "toan",
        "grade": 3,
        "book_series": "ket-noi-tri-thuc",
        "source_url": "https://loigiaihay.com/...",
        "char_count": 512
    }
"""

import re
import json
import time
import argparse
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    import requests
    from bs4 import BeautifulSoup
    from tqdm import tqdm
except ImportError:
    print("Install dependencies: pip install requests beautifulsoup4 tqdm")
    raise

BASE_URL = "https://loigiaihay.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "vi-VN,vi;q=0.9",
}

# NOTE: Keep DELAY >= 1.0 to avoid sending requests too aggressively.
DELAY = 1.2  # seconds between requests

# ── SGK catalog ────────────────────────────────────────────────────
# Format: (subject_key, grade, book_series, category_url)
SGK_CATALOG = [
    # Math — Knowledge Connection
    ("toan", 1, "ket-noi-tri-thuc", "/sgk-toan-1-ket-noi-tri-thuc-c1139.html"),
    (
        "toan",
        2,
        "ket-noi-tri-thuc",
        "/toan-lop-2-ket-noi-tri-thuc-voi-cuoc-song-c625.html",
    ),
    ("toan", 3, "ket-noi-tri-thuc", "/sgk-toan-3-ket-noi-tri-thuc-c813.html"),
    ("toan", 4, "ket-noi-tri-thuc", "/sgk-toan-4-ket-noi-tri-thuc-c1398.html"),
    ("toan", 5, "ket-noi-tri-thuc", "/sgk-toan-5-ket-noi-tri-thuc-c1728.html"),
    (
        "toan",
        6,
        "ket-noi-tri-thuc",
        "/toan-lop-6-ket-noi-tri-thuc-voi-cuoc-song-c643.html",
    ),
    ("toan", 7, "ket-noi-tri-thuc", "/sgk-toan-7-ket-noi-tri-thuc-c807.html"),
    ("toan", 8, "ket-noi-tri-thuc", "/sgk-toan-8-ket-noi-tri-thuc-c1390.html"),
    ("toan", 9, "ket-noi-tri-thuc", "/sgk-toan-9-ket-noi-tri-thuc-c1748.html"),
    # Vietnamese — Knowledge Connection (add after verifying URL)
    # ("tieng-viet", 3, "ket-noi-tri-thuc", "/sgk-tieng-viet-3-ket-noi-tri-thuc-cXXX.html"),
]


def get_soup(url: str) -> BeautifulSoup | None:
    """Fetch a page and return BeautifulSoup. Retry 2 times if error."""
    full_url = url if url.startswith("http") else BASE_URL + url
    for attempt in range(3):
        try:
            resp = requests.get(full_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            if attempt == 2:
                print(f"  ⚠ Skip {url}: {e}")
                return None
            time.sleep(2**attempt)


def get_lesson_links(category_url: str) -> list[tuple[str, str]]:
    """
    Get lesson links (url, title) of all lessons in an SGK category.
    Pattern: <a href="..." title="Toán lớp 3 trang ...">...</a>
    """
    soup = get_soup(category_url)
    if not soup:
        return []

    links = []
    for a in soup.find_all("a", href=True, title=True):
        href = str(a["href"])
        title = str(a["title"]).strip()
        # Only take lesson URLs (pattern /...-a\d+.html, not -c\d+)
        if re.search(r"-a\d+\.html$", href) and len(title) > 10:
            links.append((href, title))

    # Remove duplicates, keep first occurrence
    seen = set()
    unique = []
    for href, title in links:
        if href not in seen:
            seen.add(href)
            unique.append((href, title))

    return unique


def extract_content(soup: BeautifulSoup) -> str:
    # Remove unnecessary tags
    for tag in soup.find_all(
        ["script", "style", "nav", "footer", "iframe", "ins", "noscript"]
    ):
        tag.decompose()
    for cls in [
        "n-left-menu",  # sidebar listing all lessons — must strip before extracting
        "Choose-fast",  # tab navigation bar inside article (Hoạt động / Luyện tập 1 / Lý thuyết)
        "related",
        "comment",
        "ads",
        "social",
        "breadcrumb",
        "sidebar",
        "popup",
        "cookie",
        "header",
        "navigation",
        "binh-luan",
        "chia-se",
        "bao-loi",
        "feedback",
        "rating",
        "binhchon",
        "cac-bai-khac",
    ]:
        for tag in soup.find_all(class_=re.compile(cls, re.I)):
            tag.decompose()

    # #box-content is the actual article div; content_box is the outer wrapper that includes the sidebar
    content_block = soup.find(id="box-content")
    if not content_block:
        content_block = soup.find(class_=re.compile(r"content_article", re.I))

    target = content_block or soup.find("body") or soup
    text = target.get_text(separator="\n", strip=True)

    # Clean up
    text = re.sub(r"&[a-z]+;", " ", text)
    text = text.replace("\xa0", " ")  # non-breaking space → regular space
    text = re.sub(r"http\S+", "", text)  # remove links
    text = re.sub(r"\n{3,}", "\n\n", text)  # max 2 newlines
    text = re.sub(r"[ \t]+", " ", text)

    lines = text.split("\n")
    lines = [
        l
        for l in lines  # noqa: E741
        if not any(
            k in l
            for k in [
                "Bình luận",
                "Chia sẻ",
                "Bình chọn",
                "Báo lỗi",
                "Góp ý",
                "Lựa chọn câu để xem",
                "Luyện Bài Tập",
                "Xem ngay",
                "phiếu",
                "Video hướng dẫn",
                "Bài tiếp theo",
                "Xem chi tiết",
                ">> Xem",
            ]
        )
    ]
    lines = [l for l in lines if len(l.strip()) >= 10]  # noqa: E741

    text = "\n".join(lines)

    return text.strip()


splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    separators=[
        "\n#{1,6} ",
        "```\n",
        "\n\\*\\*\\*+\n",
        "\n---+\n",
        "\n___+\n",
        "\n\n",
        "\n",
        " ",
        "",
    ],
)


def chunk_text(text: str) -> list[str]:
    return splitter.split_text(text)


def _is_toc_chunk(text: str) -> bool:
    """Return True if >55% of non-empty lines are table-of-contents entries like 'Bài 5:' or 'Chủ đề 3:'."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return True
    toc_lines = sum(1 for line in lines if re.match(r"^(Bài|Chủ đề)\s+\d+", line))
    return toc_lines / len(lines) > 0.55


def make_chunk_id(subject: str, grade: int, series: str, url: str, idx: int) -> str:
    slug = re.sub(r"[^a-z0-9]", "-", url.split("/")[-1].replace(".html", ""))
    slug = re.sub(r"-+", "-", slug)[:40]
    return f"{subject}{grade}-{series[:4]}-{slug}-c{idx}"


def crawl_book(
    subject: str, grade: int, series: str, category_url: str, output_file
) -> int:
    """Crawl, chunk all lessons from a textbook series, save chunks to output file (jsonl)."""
    print(f"\n📚 {subject.upper()} lớp {grade} ({series})")
    lesson_links = get_lesson_links(category_url)
    print(f"   Found {len(lesson_links)} lessons")

    total_chunks = 0
    for url, title in tqdm(lesson_links, desc=f"  Grade {grade}", unit="lessons"):
        time.sleep(DELAY)
        soup = get_soup(url)
        if not soup:
            continue

        content = extract_content(soup)
        if len(content) < 100:
            continue  # Skip empty/error pages

        chunks = [c for c in chunk_text(content) if not _is_toc_chunk(c)]
        for idx, chunk in enumerate(chunks):
            record = {
                "id": make_chunk_id(subject, grade, series, url, idx),
                "title": title,
                "content": chunk,
                "subject": subject,
                "grade": grade,
                "book_series": series,
                "source_url": BASE_URL + url if not url.startswith("http") else url,
                "char_count": len(chunk),
            }
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            total_chunks += 1

    print(f"   ✅ {total_chunks} chunks")
    return total_chunks


def main():
    parser = argparse.ArgumentParser(description="Crawl SGK from loigiaihay.com")
    parser.add_argument("--grades", nargs="+", type=int, help="Grades, e.g., 3 4 5")
    parser.add_argument("--subjects", nargs="+", help="Subjects, e.g., toan tieng-viet")
    parser.add_argument("--all", action="store_true", help="Crawl all books in catalog")
    parser.add_argument("--output", default="data/sgk_chunks.jsonl")
    args = parser.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    # Filter catalog by arguments
    catalog = SGK_CATALOG
    if not args.all:
        if args.grades:
            catalog = [c for c in catalog if c[1] in args.grades]
        if args.subjects:
            catalog = [c for c in catalog if c[0] in args.subjects]

    if not catalog:
        print("No matching items found. Use --all or specify --grades/--subjects")
        return

    print(f"🚀 Starting to crawl {len(catalog)} textbooks → {args.output}")
    total = 0
    with open(args.output, "w", encoding="utf-8") as f:
        for subject, grade, series, url in catalog:
            total += crawl_book(subject, grade, series, url, f)

    print(f"\n🎉 Finished! Total {total} chunks → {args.output}")
    print("   Next step: python ingest_qdrant.py --input", args.output)


if __name__ == "__main__":
    main()
