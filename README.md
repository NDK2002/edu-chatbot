# 📚 AI Chatbot Giáo Dục — Trẻ Em Dân Tộc Thiểu Số

Chatbot hỗ trợ học sinh Tiểu học & THCS dân tộc H'Mông học Toán, Tiếng Việt, Khoa học qua giao diện **song ngữ Việt–H'Mông**. Giáo viên có thể dùng để soạn giáo án phù hợp văn hóa địa phương.

---

## 🐳 Khởi động nhanh (Docker Compose)

```bash
# 1. Clone repo
git clone https://github.com/<your-org>/edu-chatbot.git
cd edu-chatbot

# 2. Copy và điền biến môi trường
cp .env.example .env
# Điền GEMINI_API_KEY vào .env

# 3. Khởi động toàn bộ stack
docker compose up -d

# 4. Nạp dữ liệu SGK vào Qdrant (chạy 1 lần)
docker compose exec backend python scripts/ingest_kb.py
```

Sau khi chạy xong, truy cập:
- **Web app (học sinh / giáo viên):** http://localhost:3000
- **Qdrant Dashboard:** http://localhost:6333/dashboard
- **API docs:** http://localhost:8000/docs

---

## 🏗️ Cấu trúc Docker Compose

```
services:
  frontend        → Next.js (port 3000)
  backend         → FastAPI + LangChain (port 8000)
  qdrant          → Vector DB (port 6333)
  redis           → Offline cache (port 6379)
  whisper         → Speech-to-text server (port 9000)
  sympy-solver    → Bộ giải Toán (port 8001)

volumes:
  qdrant_data     → Lưu trữ KB embeddings
  redis_data      → Persistent cache (tuỳ chọn)
  kb_raw          → File SGK gốc (PDF, DOCX)
```

Redis đảm nhận hai vai trò:
- **Server-side cache** — cùng câu hỏi từ nhiều học sinh khác nhau gọi lên server, Redis cache response Qdrant & Gemini lại, không gọi lại lần hai → tiết kiệm quota, giảm latency
- **Session cache** — lưu trạng thái hội thoại ngắn hạn của từng học sinh trong phiên học

> ⚠️ **Offline mode không dùng Redis** — Redis chạy trên server, thiết bị mất mạng thì không kết nối được. Offline dùng **SQLite local** trên thiết bị: khi có mạng app prefetch bài học về lưu sẵn, mất mạng đọc từ SQLite.

---

## ⚡ Kiến trúc xử lý

**Text input** → Vector Search (Qdrant) → trả kết quả ngay nếu similarity score ≥ 0.82  
**Voice / Ảnh** → STT/OCR (Whisper / Google Vision) → text → Vector Search  
**Fallback** → Gọi Gemini 2.0 Flash API khi score < 0.82  
**Bài Toán** → SymPy Solver (không để LLM tự tính số)

---

## ⚠️ Rủi ro & Giải pháp

| Rủi ro | Mức độ | Giải pháp |
|--------|--------|-----------|
| **Mất kết nối Internet vùng sâu** | 🔴 Cao | Offline mode dùng **SQLite local** trên thiết bị — khi có mạng app prefetch bài học về lưu sẵn, mất mạng vẫn đọc được. Redis chỉ dùng ở server-side cache, không liên quan offline |
| **AI tạo nội dung không phù hợp trẻ em** | 🔴 Cao | Content Safety layer độc lập (chạy trước mọi output), whitelist chủ đề giáo dục, blocklist nghiêm ngặt |
| **Từ điển H'Mông chưa đầy đủ / sai** | 🟡 Trung bình | Có thể bổ sung qua `scripts/add_vocab.py`; giáo viên bản địa review trước khi nạp vào KB |
| **Thiết bị học sinh cấu hình thấp** | 🟡 Trung bình | Frontend tối ưu cho Android ≥ 2GB RAM; ảnh nén client-side trước khi upload; hạn chế API call với vector search |
| **Học sinh phụ thuộc AI, không tự suy nghĩ** | 🟡 Trung bình | Chế độ "Gợi ý từng bước" — AI hỏi ngược lại trước, chỉ đưa đáp án khi học sinh đã thử |
| **Hallucination ở phần Toán** | 🟢 Thấp | SymPy Solver tính độc lập; LLM chỉ diễn giải lời giải bằng ngôn ngữ tự nhiên, không tự tính số |
| **Vượt quota Gemini API (1500 req/ngày free)** | 🟢 Thấp | Vector search xử lý phần lớn text query, chỉ fallback LLM khi thực sự cần; theo dõi quota qua `/metrics` |

---

## 🔧 Biến môi trường (.env)

```env
# Bắt buộc
GEMINI_API_KEY=your_gemini_api_key_here

# Qdrant (mặc định dùng local Docker)
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION_MATH=edu_kb

# Redis (offline cache)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_CACHE_TTL=86400        # TTL cache tính bằng giây (mặc định 24h)
REDIS_MAX_MEMORY=256mb       # Giới hạn bộ nhớ Redis

# Whisper
WHISPER_MODEL=small          # tiny | small | medium
WHISPER_LANGUAGE=vi          # vi | hmong

# Ngưỡng vector search
VECTOR_SCORE_THRESHOLD=0.82

# Content Safety
CONTENT_SAFETY_MODE=strict   # strict | moderate

# Google Vision OCR (tuỳ chọn)
GOOGLE_VISION_API_KEY=
```

---

## 📁 Cấu trúc thư mục

```
edu-chatbot/
├── docker-compose.yml
├── .env.example
├── README.md
├── frontend/              # Next.js app
├── backend/               # FastAPI + LangChain
│   ├── main.py
│   ├── routers/
│   │   ├── chat.py        # Vector search + LLM fallback
│   │   ├── solver.py      # SymPy Toán
│   │   └── teacher.py     # Soạn giáo án
│   ├── services/
│   │   ├── vector_search.py
│   │   ├── gemini.py
│   │   ├── content_safety.py
│   │   └── translator.py  # Việt ↔ H'Mông
│   └── scripts/
│       ├── ingest_kb.py   # Nạp SGK vào Qdrant
│       └── add_vocab.py   # Thêm từ điển H'Mông
├── sympy-solver/          # Service giải Toán riêng
├── whisper/               # STT server
└── kb_raw/                # SGK PDF + từ điển (không commit)
```

---

## 📝 Ghi chú

- KB data (`kb_raw/`) **không được commit** vào repo vì lý do bản quyền SGK — tự chuẩn bị hoặc liên hệ nhóm.
- Lần đầu `ingest_kb.py` chạy khoảng 5–15 phút tùy lượng tài liệu.
- Để thêm ngôn ngữ mới (Tày–Nùng, Ê Đê...), bổ sung từ điển tương ứng và chạy lại `ingest_kb.py`.
