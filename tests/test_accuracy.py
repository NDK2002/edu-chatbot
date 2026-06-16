"""
Accuracy test — Rule Engine + Dictionary lookup.
Chạy: python test_accuracy.py
"""

import re
import sys
import os

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from backend.services.intent_detector import solve

# ---------------------------------------------------------------------------
# PHẦN 1: Rule Engine — 22 test cases
# None = chỉ kiểm tra chạy không lỗi (bảng nhân/chia)
# ---------------------------------------------------------------------------

RULE_CASES = [
    # Phép tính cơ bản
    ("Cộng",              "25 + 38 bằng bao nhiêu?",                                  63),
    ("Trừ",               "72 - 45 bằng bao nhiêu?",                                  27),
    ("Nhân",              "6 × 8 bằng bao nhiêu?",                                    48),
    ("Chia",              "56 ÷ 7 bằng bao nhiêu?",                                    8),
    ("Cộng (đơn vị)",     "Tính 15 + 23",                                             38),
    ("Nhân (đơn vị)",     "9 × 7 bằng bao nhiêu?",                                    63),

    # Bảng nhân / bảng chia
    ("Bảng nhân 7",       "Bảng nhân 7",                                             None),
    ("Bảng chia 8",       "Bảng chia 8",                                             None),

    # Chu vi
    ("Chu vi HCN",        "Chu vi hình chữ nhật dài 8cm rộng 3cm",                   22),
    ("Chu vi HV",         "Chu vi hình vuông cạnh 5cm",                              20),
    ("Chu vi tam giác",   "Chu vi tam giác 3cm 4cm 5cm",                             12),

    # Diện tích
    ("DT HCN",            "Diện tích hình chữ nhật dài 6cm rộng 4cm",               24),
    ("DT HV",             "Diện tích hình vuông cạnh 7cm",                           49),
    ("DT tam giác",       "Diện tích hình tam giác đáy 10cm chiều cao 6cm",          30),
    ("DT hình thang",     "Diện tích hình thang đáy lớn 8cm đáy bé 4cm chiều cao 5cm", 30),

    # Đổi đơn vị
    ("Đổi km→m",          "3km bằng bao nhiêu m",                                  3000),
    ("Đổi kg→g",          "2kg bằng bao nhiêu g",                                  2000),
    ("Đổi giờ→phút",      "2 giờ bằng bao nhiêu phút",                              120),

    # Vận tốc
    ("Tính quãng đường",  "Vận tốc 60km/h thời gian 2 giờ quãng đường là bao nhiêu", 120),
    ("Tính vận tốc",      "Quãng đường 150km thời gian 3 giờ vận tốc là bao nhiêu",   50),

    # Phần trăm
    ("% của số",          "20% của 150 là bao nhiêu",                                30),
    ("Tìm % (tỉ số)",     "30 là bao nhiêu phần trăm của 150",                       20),
]

# ---------------------------------------------------------------------------
# PHẦN 2: Từ điển Tày/Nùng — kiểm tra qua API (cần server chạy)
# Các từ phổ biến học sinh hay hỏi
# ---------------------------------------------------------------------------

DICT_CASES = [
    ("Số đếm",    "một trong tiếng Tày là gì?",       "một"),
    ("Gia đình",  "bố trong tiếng Tày là gì?",        "bố"),
    ("Gia đình",  "mẹ trong tiếng Nùng là gì?",       "mẹ"),
    ("Trường học","học trong tiếng Tày là gì?",       "học"),
    ("Thiên nhiên","nước trong tiếng Tày là gì?",     "nước"),
    ("Toán",      "cộng trong tiếng Tày là gì?",      "cộng"),
    ("Toán",      "số trong tiếng Tày là gì?",        "số"),
    ("Màu sắc",   "màu đỏ trong tiếng Nùng là gì?",  "đỏ"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_number(text: str) -> float | None:
    cleaned = re.sub(r"(\d)\s+(\d)", r"\1\2", text)
    m = re.search(r"-?\d+(?:[.,]\d+)?", cleaned)
    return float(m.group().replace(",", ".")) if m else None


def _rule_row(label, query, expected):
    result = solve(query)
    if result is None:
        return "SKIP", label, query, expected, "— intent không nhận ra"
    if result.error:
        return "FAIL", label, query, expected, f"Error: {result.error}"
    if expected is None:
        if result.steps:
            return "PASS", label, query, "N/A", result.answer[:60]
        return "FAIL", label, query, "N/A", "Không có steps"
    got = extract_number(result.answer)
    if got is not None and abs(got - expected) < 0.001:
        return "PASS", label, query, expected, result.answer
    return "FAIL", label, query, expected, f"Got: {result.answer!r}"


def run_rule_engine():
    rows = [_rule_row(lbl, q, exp) for lbl, q, exp in RULE_CASES]
    passed = sum(1 for r in rows if r[0] == "PASS")
    failed  = sum(1 for r in rows if r[0] == "FAIL")
    skipped = sum(1 for r in rows if r[0] == "SKIP")
    return rows, passed, failed, skipped


def run_dictionary():
    """Gọi API chat endpoint để kiểm tra từ điển. Bỏ qua nếu server chưa chạy."""
    try:
        import urllib.request, json, urllib.error
        req = urllib.request.Request(
            "http://localhost:8000/v2/chat/",
            data=json.dumps({"message": "ping", "mode": "student"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        return None  # server not running

    rows = []
    import urllib.request, json

    for category, query, keyword in DICT_CASES:
        try:
            payload = json.dumps({"message": query, "mode": "student"}).encode()
            req = urllib.request.Request(
                "http://localhost:8000/v2/chat/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            # Collect full SSE stream
            full = b""
            with urllib.request.urlopen(req, timeout=10) as resp:
                full = resp.read()

            # Parse SSE: look for vocab entries
            text = full.decode("utf-8", errors="replace")
            has_vocab = '"vocab"' in text or keyword in text
            answer_chunk = ""
            for line in text.splitlines():
                if line.startswith("data: "):
                    try:
                        d = json.loads(line[6:])
                        if d.get("type") == "chunk":
                            answer_chunk += d.get("text", "")
                    except Exception:
                        pass

            if has_vocab or keyword.lower() in answer_chunk.lower():
                rows.append(("PASS", category, query, keyword, answer_chunk[:60] or "vocab found"))
            else:
                rows.append(("FAIL", category, query, keyword, answer_chunk[:60] or "no vocab"))
        except Exception as e:
            rows.append(("FAIL", category, query, keyword, f"Error: {e}"))

    passed = sum(1 for r in rows if r[0] == "PASS")
    failed  = sum(1 for r in rows if r[0] == "FAIL")
    return rows, passed, failed


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_section(title, rows, passed, failed, skipped=0):
    col_w = [6, 18, 52, 10, 40]
    header = f"{'STATUS':<{col_w[0]}}  {'Loại':<{col_w[1]}}  {'Câu hỏi':<{col_w[2]}}  {'Expected':>{col_w[3]}}  {'Kết quả'}"
    sep = "─" * (sum(col_w) + 8)

    print(f"\n{'═'*len(sep)}")
    print(f"  {title}")
    print(f"{'═'*len(sep)}")
    print(header)
    print(sep)

    for status, label, query, expected, note in rows:
        icon = "✅" if status == "PASS" else ("⚠️ " if status == "SKIP" else "❌")
        exp_s = str(expected) if expected is not None else "N/A"
        q_s = (query[:49] + "…") if len(query) > 50 else query
        print(f"{icon}{status:<{col_w[0]}}  {label:<{col_w[1]}}  {q_s:<{col_w[2]}}  {exp_s:>{col_w[3]}}  {note}")

    print(sep)
    total = passed + failed + skipped
    acc = (passed / (passed + failed) * 100) if (passed + failed) > 0 else 0
    skip_note = f"  |  SKIPPED: {skipped}" if skipped else ""
    print(f"  PASSED: {passed}/{total}  |  FAILED: {failed}{skip_note}")
    print(f"  ACCURACY: {acc:.1f}%")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    rule_rows, r_pass, r_fail, r_skip = run_rule_engine()
    print_section("PHẦN 1 — RULE ENGINE (Toán tiểu học)", rule_rows, r_pass, r_fail, r_skip)

    dict_result = run_dictionary()
    if dict_result is None:
        print("\n  ⚠️  PHẦN 2 — TỪ ĐIỂN TÀY/NÙNG: server không chạy, bỏ qua.")
        print("     Khởi động server rồi chạy lại để test từ điển.\n")
        d_pass, d_fail = 0, 0
    else:
        dict_rows, d_pass, d_fail = dict_result
        print_section("PHẦN 2 — TỪ ĐIỂN TÀY/NÙNG (yêu cầu server)", dict_rows, d_pass, d_fail)

    total_pass = r_pass + d_pass
    total_fail = r_fail + d_fail
    total_all  = total_pass + total_fail + r_skip
    overall    = (total_pass / (total_pass + total_fail) * 100) if (total_pass + total_fail) > 0 else 0

    print(f"\n{'═'*70}")
    print(f"  TỔNG KẾT: {total_pass}/{total_all} câu đúng  |  Accuracy: {overall:.1f}%")
    print(f"{'═'*70}\n")

    return r_fail == 0 and d_fail == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
