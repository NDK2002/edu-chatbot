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
import os
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
    from tqdm import tqdm
except ImportError:
    print("Cài dependencies trước: pip install requests beautifulsoup4 tqdm")
    raise

BASE_URL = "https://loigiaihay.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "vi-VN,vi;q=0.9",
}
DELAY = 1.2  # giây giữa mỗi request — lịch sự với server

# ── Danh mục SGK cần crawl ────────────────────────────────────────────────────
# Format: (subject_key, grade, book_series, category_url)
SGK_CATALOG = [
    # Toán — Kết nối tri thức
    ("toan", 1, "ket-noi-tri-thuc", "/sgk-toan-1-ket-noi-tri-thuc-c1139.html"),
    ("toan", 2, "ket-noi-tri-thuc", "/sgk-toan-2-ket-noi-tri-thuc-c813.html"),   # placeholder — cần verify
    ("toan", 3, "ket-noi-tri-thuc", "/sgk-toan-3-ket-noi-tri-thuc-c813.html"),
    ("toan", 4, "ket-noi-tri-thuc", "/sgk-toan-4-ket-noi-tri-thuc-c1398.html"),
    ("toan", 5, "ket-noi-tri-thuc", "/sgk-toan-5-ket-noi-tri-thuc-c1728.html"),
    # Tiếng Việt — Kết nối tri thức (thêm sau khi verify URL)
    # ("tieng-viet", 3, "ket-noi-tri-thuc", "/sgk-tieng-viet-3-ket-noi-tri-thuc-cXXX.html"),
]


def get_soup(url: str) -> BeautifulSoup | None:
    """Fetch một trang và trả về BeautifulSoup. Retry 2 lần nếu lỗi."""
    full_url = url if url.startswith("http") else BASE_URL + url
    for attempt in range(3):
        try:
            resp = requests.get(full_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            if attempt == 2:
                print(f"  ⚠ Bỏ qua {url}: {e}")
                return None
            time.sleep(2 ** attempt)


def get_lesson_links(category_url: str) -> list[tuple[str, str]]:
    """
    Lấy danh sách (url, title) của tất cả bài học trong một category SGK.
    Pattern: <a href="..." title="Toán lớp 3 trang ...">...</a>
    """
    soup = get_soup(category_url)
    if not soup:
        return []

    links = []
    for a in soup.find_all("a", href=True, title=True):
        href = a["href"]
        title = a["title"].strip()
        # Chỉ lấy bài học (URL dạng /...-a\d+.html, không phải category -c\d+)
        if re.search(r"-a\d+\.html$", href) and len(title) > 10:
            links.append((href, title))

    # Dedup giữ thứ tự
    seen = set()
    unique = []
    for href, title in links:
        if href not in seen:
            seen.add(href)
            unique.append((href, title))

    return unique


def extract_content(soup: BeautifulSoup) -> str:
    """
    Extract text nội dung bài học từ một trang loigiaihay.
    Loại bỏ: nav, ads, comments, scripts, related-articles.
    """
    # Xóa các phần không cần
    for tag in soup.find_all(["script", "style", "nav", "footer",
                               "iframe", "ins", "noscript"]):
        tag.decompose()
    for cls in ["related", "comment", "ads", "social", "breadcrumb",
                "sidebar", "popup", "cookie", "header", "navigation"]:
        for tag in soup.find_all(class_=re.compile(cls, re.I)):
            tag.decompose()

    # Tìm block nội dung chính qua article_id
    content_block = soup.find(id=re.compile(r"content_article"))
    if not content_block:
        # fallback: thử class article
        content_block = soup.find(class_=re.compile(r"article|content-detail", re.I))

    target = content_block or soup.find("body") or soup
    text = target.get_text(separator="\n", strip=True)

    # Làm sạch
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"http\S+", "", text)          # xóa links
    text = re.sub(r"\n{3,}", "\n\n", text)        # max 2 newlines liên tiếp
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def chunk_text(text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
    """
    Chia text thành các chunk nhỏ có overlap để embed tốt hơn.
    Ưu tiên cắt ở boundary đoạn văn (\n\n).
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
                # Overlap: giữ lại phần cuối của chunk trước
                current = current[-overlap:] + "\n\n" + para
                current = current.strip()
            else:
                # Para quá dài, cắt theo ký tự
                for i in range(0, len(para), max_chars - overlap):
                    chunks.append(para[i:i + max_chars])
                current = ""

    if current:
        chunks.append(current)

    return [c for c in chunks if len(c) > 50]  # bỏ chunks quá ngắn


def make_chunk_id(subject: str, grade: int, series: str, url: str, idx: int) -> str:
    slug = re.sub(r"[^a-z0-9]", "-", url.split("/")[-1].replace(".html", ""))
    slug = re.sub(r"-+", "-", slug)[:40]
    return f"{subject}{grade}-{series[:4]}-{slug}-c{idx}"


def crawl_book(subject: str, grade: int, series: str,
               category_url: str, output_file) -> int:
    """Crawl toàn bộ một cuốn SGK, ghi chunks vào output_file (jsonl)."""
    print(f"\n📚 {subject.upper()} lớp {grade} ({series})")
    lesson_links = get_lesson_links(category_url)
    print(f"   Tìm thấy {len(lesson_links)} bài")

    total_chunks = 0
    for url, title in tqdm(lesson_links, desc=f"  Lớp {grade}", unit="bài"):
        time.sleep(DELAY)
        soup = get_soup(url)
        if not soup:
            continue

        content = extract_content(soup)
        if len(content) < 100:
            continue  # bỏ trang rỗng/lỗi

        chunks = chunk_text(content)
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
    parser = argparse.ArgumentParser(description="Crawl SGK từ loigiaihay.com")
    parser.add_argument("--grades", nargs="+", type=int,
                        help="Lớp cụ thể, vd: 3 4 5")
    parser.add_argument("--subjects", nargs="+",
                        help="Môn học: toan tieng-viet")
    parser.add_argument("--all", action="store_true",
                        help="Crawl toàn bộ SGK trong catalog")
    parser.add_argument("--output", default="data/sgk_chunks.jsonl")
    args = parser.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    # Lọc catalog theo tham số
    catalog = SGK_CATALOG
    if not args.all:
        if args.grades:
            catalog = [c for c in catalog if c[1] in args.grades]
        if args.subjects:
            catalog = [c for c in catalog if c[0] in args.subjects]

    if not catalog:
        print("Không có mục nào phù hợp. Dùng --all hoặc chỉ định --grades/--subjects")
        return

    print(f"🚀 Bắt đầu crawl {len(catalog)} cuốn SGK → {args.output}")
    total = 0
    with open(args.output, "w", encoding="utf-8") as f:
        for subject, grade, series, url in catalog:
            total += crawl_book(subject, grade, series, url, f)

    print(f"\n🎉 Hoàn tất! Tổng cộng {total} chunks → {args.output}")
    print("   Bước tiếp: python ingest_qdrant.py --input", args.output)


if __name__ == "__main__":
    main()
