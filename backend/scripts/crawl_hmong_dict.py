"""
crawl_hmong_dict.py
===================
Xây dựng từ điển Việt–H'Mông từ 2 nguồn:

1. Wiktionary (White Hmong / mww) — ~825 lemmas có sẵn
   → Crawl định nghĩa tiếng Anh → dịch sang tiếng Việt

2. Gemini API — sinh từ vựng cơ bản trong SGK tiểu học
   → ~500 từ thông dụng nhất (số, màu, gia đình, thiên nhiên...)

Output:
    data/hmong_viet_dict.json  — dict {hmong_word: {vi: str, en: str, category: str}}
    data/hmong_viet_dict.jsonl — dạng chunks để nạp vào Qdrant

Cách dùng:
    pip install requests tqdm google-generativeai
    export GEMINI_API_KEY=your_key
    python crawl_hmong_dict.py --wiktionary   # Chỉ crawl Wiktionary
    python crawl_hmong_dict.py --gemini       # Chỉ dùng Gemini
    python crawl_hmong_dict.py --all          # Cả hai (khuyến nghị)
"""

import re
import json
import time
import argparse
import os
from pathlib import Path

try:
    import requests
    from tqdm import tqdm
except ImportError:
    print("pip install requests tqdm")
    raise


WIKTIONARY_API = "https://en.wiktionary.org/w/api.php"
HEADERS = {"User-Agent": "EduChatbot-Research/1.0 (educational nonprofit)"}
DELAY = 0.5


# ── PHẦN 1: Crawl Wiktionary ──────────────────────────────────────────────────

def get_all_hmong_lemmas() -> list[str]:
    """Lấy toàn bộ White Hmong lemmas từ Wiktionary (khoảng 825 từ)."""
    lemmas = []
    cmcontinue = None

    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": "Category:White_Hmong_lemmas",
            "cmlimit": 500,
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        resp = requests.get(WIKTIONARY_API, params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        members = data.get("query", {}).get("categorymembers", [])
        lemmas.extend(m["title"] for m in members)

        cont = data.get("continue", {})
        cmcontinue = cont.get("cmcontinue")
        if not cmcontinue:
            break
        time.sleep(DELAY)

    print(f"   Tìm thấy {len(lemmas)} White Hmong lemmas")
    return lemmas


def parse_hmong_entry(wikitext: str) -> dict | None:
    """
    Parse wikitext của một từ H'Mông.
    Extract: định nghĩa tiếng Anh, từ loại, ví dụ.
    """
    # Tìm section White Hmong
    hmong_section = re.search(
        r"==White Hmong==(.*?)(?:^==[^=]|\Z)",
        wikitext, re.S | re.M
    )
    if not hmong_section:
        return None

    section = hmong_section.group(1)

    # Lấy từ loại
    pos = "unknown"
    for p in ["Noun", "Verb", "Adjective", "Adverb", "Classifier", "Pronoun"]:
        if f"==={p}===" in section or f"====={p}=====" in section:
            pos = p.lower()
            break

    # Lấy definitions (dòng bắt đầu bằng # không phải #*)
    defs = re.findall(r"^# (.+)$", section, re.M)
    definitions_en = []
    for d in defs:
        # Xóa wiki markup
        d = re.sub(r"\[\[([^\]|]+\|)?([^\]]+)\]\]", r"\2", d)
        d = re.sub(r"\{\{[^}]+\}\}", "", d)
        d = re.sub(r"'''|''", "", d)
        d = d.strip()
        if d and len(d) > 1:
            definitions_en.append(d)

    if not definitions_en:
        return None

    return {
        "en": "; ".join(definitions_en[:3]),  # max 3 nghĩa
        "pos": pos,
    }


def fetch_wiktionary_entry(title: str) -> dict | None:
    """Fetch và parse một entry từ Wiktionary."""
    params = {
        "action": "parse",
        "page": title,
        "prop": "wikitext",
        "format": "json",
    }
    try:
        resp = requests.get(WIKTIONARY_API, params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
        entry = parse_hmong_entry(wikitext)
        if entry:
            entry["hmong"] = title
        return entry
    except Exception:
        return None


def translate_en_to_vi_batch(entries: list[dict]) -> list[dict]:
    """
    Dùng Gemini để dịch định nghĩa tiếng Anh sang tiếng Việt hàng loạt.
    Gửi 20 từ một lần để tiết kiệm API calls.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("   ⚠ Không có GEMINI_API_KEY — bỏ qua bước dịch, giữ định nghĩa tiếng Anh")
        for e in entries:
            e["vi"] = e["en"]  # fallback
        return entries

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
    except ImportError:
        print("   pip install google-generativeai")
        for e in entries:
            e["vi"] = e["en"]
        return entries

    BATCH = 20
    for i in tqdm(range(0, len(entries), BATCH), desc="  Dịch sang tiếng Việt"):
        batch = entries[i:i + BATCH]
        lines = "\n".join(f'{j+1}. "{e["hmong"]}" = {e["en"]}' for j, e in enumerate(batch))
        prompt = f"""Dịch các định nghĩa tiếng Anh sau sang tiếng Việt ngắn gọn (1-5 từ mỗi nghĩa).
Đây là từ vựng tiếng H'Mông dùng trong giáo dục tiểu học Việt Nam.
Trả lời chỉ JSON array, không giải thích: [{{"vi": "..."}}, ...]

{lines}"""
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            text = re.sub(r"```json|```", "", text).strip()
            translations = json.loads(text)
            for j, entry in enumerate(batch):
                if j < len(translations):
                    entry["vi"] = translations[j].get("vi", entry["en"])
                else:
                    entry["vi"] = entry["en"]
        except Exception as e:
            print(f"   Lỗi dịch batch {i}: {e}")
            for entry in batch:
                entry["vi"] = entry["en"]
        time.sleep(0.5)

    return entries


def crawl_wiktionary() -> list[dict]:
    """Crawl toàn bộ White Hmong từ Wiktionary."""
    print("\n📖 Crawl Wiktionary (White Hmong)...")
    lemmas = get_all_hmong_lemmas()

    entries = []
    for lemma in tqdm(lemmas, desc="  Fetch entries"):
        entry = fetch_wiktionary_entry(lemma)
        if entry:
            entries.append(entry)
        time.sleep(DELAY)

    print(f"   Parse được {len(entries)}/{len(lemmas)} entries")
    entries = translate_en_to_vi_batch(entries)
    return entries


# ── PHẦN 2: Gemini sinh từ vựng SGK ─────────────────────────────────────────

VOCABULARY_CATEGORIES = [
    ("số_đếm", "các số từ 0 đến 100, số thứ tự, phép tính cộng trừ nhân chia"),
    ("màu_sắc", "màu đỏ xanh vàng trắng đen nâu tím cam hồng xám"),
    ("gia_đình", "bố mẹ anh chị em ông bà cô chú dì"),
    ("thiên_nhiên_vùng_cao", "núi rừng sông suối ruộng nương ngô lúa cây"),
    ("động_vật", "trâu bò lợn gà chó mèo ngựa chim cá"),
    ("thời_gian", "ngày tháng năm sáng trưa chiều tối hôm nay hôm qua"),
    ("trường_học", "thầy cô học sinh lớp bảng sách vở bút"),
    ("cơ_thể", "đầu mắt mũi miệng tay chân bụng lưng"),
    ("nhà_cửa", "nhà bếp phòng cửa sổ bàn ghế giường"),
    ("tính_từ_cơ_bản", "to nhỏ cao thấp dài ngắn nhanh chậm nóng lạnh"),
]


def generate_hmong_vocab_gemini(category: str, description: str) -> list[dict]:
    """Dùng Gemini sinh từ vựng H'Mông cho một chủ đề."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return []

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
    except ImportError:
        return []

    prompt = f"""Tạo từ điển Việt–H'Mông (White Hmong, mww) cho chủ đề: {description}
Trả về JSON array, mỗi object gồm:
- "vi": từ tiếng Việt
- "hmong": từ H'Mông tương ứng (White Hmong / Hmoob Dawb)
- "en": nghĩa tiếng Anh
- "category": "{category}"

Chú ý: Dùng hệ thống chính tả RPA (Romanized Popular Alphabet) chuẩn của H'Mông.
Chỉ trả JSON array, không giải thích. Khoảng 15-25 từ."""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        text = re.sub(r"```json|```", "", text).strip()
        entries = json.loads(text)
        return entries if isinstance(entries, list) else []
    except Exception as e:
        print(f"   Lỗi Gemini [{category}]: {e}")
        return []


def generate_with_gemini() -> list[dict]:
    """Sinh từ vựng H'Mông bằng Gemini cho tất cả chủ đề SGK."""
    print("\n🤖 Sinh từ vựng bằng Gemini...")
    all_entries = []

    for category, description in tqdm(VOCABULARY_CATEGORIES, desc="  Chủ đề"):
        entries = generate_hmong_vocab_gemini(category, description)
        all_entries.extend(entries)
        print(f"   [{category}]: {len(entries)} từ")
        time.sleep(1)  # tránh rate limit

    return all_entries


# ── MAIN ──────────────────────────────────────────────────────────────────────

def merge_and_save(wiktionary_entries: list[dict],
                   gemini_entries: list[dict],
                   output_dir: str = "data"):
    """Merge, dedup, lưu file."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Dedup theo từ H'Mông
    seen_hmong = set()
    all_entries = []

    for entry in wiktionary_entries + gemini_entries:
        hmong_word = entry.get("hmong", "").strip().lower()
        if hmong_word and hmong_word not in seen_hmong:
            seen_hmong.add(hmong_word)
            all_entries.append({
                "hmong": entry.get("hmong", ""),
                "vi": entry.get("vi", entry.get("en", "")),
                "en": entry.get("en", ""),
                "pos": entry.get("pos", "unknown"),
                "category": entry.get("category", "wiktionary"),
                "source": "wiktionary" if "pos" in entry else "gemini",
            })

    # Lưu JSON dict
    dict_path = f"{output_dir}/hmong_viet_dict.json"
    with open(dict_path, "w", encoding="utf-8") as f:
        json.dump(
            {e["hmong"]: e for e in all_entries},
            f, ensure_ascii=False, indent=2
        )

    # Lưu JSONL chunks để nạp vào Qdrant
    chunks_path = f"{output_dir}/hmong_viet_chunks.jsonl"
    with open(chunks_path, "w", encoding="utf-8") as f:
        for i, entry in enumerate(all_entries):
            # Tạo content để embed: kết hợp cả 3 ngôn ngữ
            content = (
                f"H'Mông: {entry['hmong']}\n"
                f"Tiếng Việt: {entry['vi']}\n"
                f"English: {entry['en']}"
            )
            chunk = {
                "id": f"hmong-dict-{i:04d}",
                "title": f"Từ H'Mông: {entry['hmong']} = {entry['vi']}",
                "content": content,
                "subject": "tu-dien",
                "grade": 0,
                "book_series": "hmong-viet",
                "source_url": f"https://en.wiktionary.org/wiki/{entry['hmong']}",
                "char_count": len(content),
                "metadata": entry,
            }
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"\n✅ Lưu {len(all_entries)} từ:")
    print(f"   Dict:   {dict_path}")
    print(f"   Chunks: {chunks_path}")

    # Stats
    by_source = {}
    by_cat = {}
    for e in all_entries:
        by_source[e["source"]] = by_source.get(e["source"], 0) + 1
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1

    print("\n📊 Thống kê:")
    print("  Nguồn:", dict(sorted(by_source.items())))
    print("  Chủ đề (top 10):", dict(list(sorted(by_cat.items(),
                                                   key=lambda x: -x[1]))[:10]))


def main():
    parser = argparse.ArgumentParser(description="Xây dựng từ điển Việt–H'Mông")
    parser.add_argument("--wiktionary", action="store_true")
    parser.add_argument("--gemini", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--output", default="data")
    args = parser.parse_args()

    if not any([args.wiktionary, args.gemini, args.all]):
        parser.print_help()
        return

    wiktionary_entries = []
    gemini_entries = []

    if args.wiktionary or args.all:
        wiktionary_entries = crawl_wiktionary()

    if args.gemini or args.all:
        if not os.getenv("GEMINI_API_KEY"):
            print("⚠ GEMINI_API_KEY chưa set — bỏ qua bước Gemini")
        else:
            gemini_entries = generate_with_gemini()

    merge_and_save(wiktionary_entries, gemini_entries, args.output)


if __name__ == "__main__":
    main()
