# Edu Chatbot RAG

Chatbot giáo dục hỗ trợ học sinh vùng cao / dân tộc thiểu số học và hỏi đáp kiến thức Toán bằng tiếng Việt đơn giản, có bổ sung tra cứu từ điển Việt - Tày/Nùng khi có dữ liệu phù hợp.

Project tập trung vào việc xây dựng ứng dụng AI có khả năng hỏi đáp học tập bằng RAG, Rule Engine và LLM fallback, đồng thời hỗ trợ tra cứu từ điển Việt - Tày/Nùng trong các tình huống phù hợp.

## Tính năng chính

- Chat học sinh qua giao diện Next.js với SSE streaming.
- Backend FastAPI điều phối câu hỏi qua `orchestrator`.
- Rule Engine cho các bài Toán có quy tắc: phép tính, chu vi, diện tích, đổi đơn vị, phần trăm...
- RAG với Qdrant cho nội dung SGK / knowledge chunks.
- Vietnamese embedding và reranker thông qua AI model server riêng.
- Gemini fallback để diễn đạt câu trả lời tự nhiên.
- Dictionary search Việt - Tày/Nùng và Tày/Nùng - Việt.
- Content safety, prompt-injection detection, rate limit.
- Supabase Auth và lưu lịch sử hội thoại.
- Redis cache cho Gemini response và rate limit.
- Auto-compact lịch sử hội thoại dài.

## Tech stack

| Layer | Công nghệ |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Backend | FastAPI, Uvicorn, Python |
| Vector DB | Qdrant |
| Embedding | `AITeamVN/Vietnamese_Embedding` qua AI model server |
| Reranker | `BAAI/bge-reranker-v2-m3` qua AI model server |
| LLM | Google Gemini 2.5 Flash / Flash Lite fallback |
| Cache / rate limit | Redis |
| Auth / DB | Supabase |
| Math | Custom Rule Engine + SymPy |
| Deploy | Docker Compose |

## Kiến trúc xử lý chat

```text
Frontend Chat UI
    |
    v
Next.js API proxy
    |
    v
FastAPI /v2/chat
    |
    +-- Content Safety / Prompt Injection Check
    |
    +-- Orchestrator classify_query()
          |
          +-- MATH_CALCULATE -> Rule Engine
          +-- MATH_THEORY    -> Qdrant RAG -> Reranker
          +-- DICT_*         -> Dictionary Search -> Reranker
          +-- GENERAL        -> Gemini fallback
    |
    +-- Build RAG context + conversation history
    |
    +-- Gemini stream response
    |
    v
SSE chunks back to browser
```

Điểm quan trọng: LLM không được dùng một mình. Hệ thống chèn các lớp kiểm soát như Rule Engine, RAG, reranker, content safety và metadata nguồn để giảm hallucination và tăng khả năng kiểm chứng.

## Yêu cầu

- Docker và Docker Compose (Docker Desktop hoặc Docker Engine ≥ 24)
- Git

## Cài đặt và chạy

### 1. Clone repo

```bash
git clone <repo-url>
cd edu-chatbot
```

### 2. Tạo file môi trường

**Root `.env`** (backend + docker-compose):

```bash
cp .env.example .env
```

Điền các biến bắt buộc trong `.env`:

```env
GEMINI_API_KEY=<lấy tại https://aistudio.google.com/app/apikey>
AI_MODEL_URL=https://ai-model.ndk.id.vn
AI_MODEL_API_KEY=<key của AI model server>
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=<publishable_key>
SUPABASE_SECRET_KEY=<secret_key>
REDIS_PASSWORD=<đặt mật khẩu bất kỳ>
```

**Frontend `.env.local`** (Next.js cần `NEXT_PUBLIC_*` tại build time):

```bash
cp frontend/.env.local.example frontend/.env.local
```

Điền cùng giá trị Supabase:

```env
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable_key>
```

> **Lưu ý về AI model server:**
> - Mặc định dùng server ngoài (`AI_MODEL_URL`). Nếu có API key thì không cần thêm gì.
> - Nếu muốn chạy embedding/reranker hoàn toàn local: docker-compose đã bao gồm sẵn `infinity-embedding` (port 7997) và `infinity-reranker` (port 7998). Khi đó thêm vào `.env`:
>   ```env
>   EMBED_URL=http://infinity-embedding:7997/embeddings
>   RERANK_URL=http://infinity-reranker:7998/rerank
>   ```
>   Lần đầu khởi động sẽ tải model (~2–4 GB) vào thư mục `hf-cache/`.

### 3. Cấu hình Supabase

Tạo project trên [supabase.com](https://supabase.com), sau đó vào **SQL Editor** và chạy lần lượt các file migration trong thư mục `supabase/migrations/`:

```
001_initial.sql
002_conversations.sql
003_add_steps_to_messages.sql
004_add_vocab_to_messages.sql
005_lesson_plans.sql
```

Lấy các key từ **Project Settings → API** để điền vào `.env` và `frontend/.env.local` ở bước 2.

### 4. Khởi động services

```bash
docker compose up -d --build
```

Sau khi chạy:

- Frontend: `http://localhost:3000`
- Qdrant dashboard: `http://localhost:6333/dashboard`
- Backend API: chạy nội bộ trong Docker network tại `http://backend:8000`

Mặc định `docker-compose.yml` không expose port backend `8000` ra host. Nếu cần xem Swagger `http://localhost:8000/docs`, thêm mapping sau vào service `backend`:

```yaml
ports:
  - "8000:8000"
```

rồi chạy lại:

```bash
docker compose up -d --build backend
```

### 5. Nạp dữ liệu vào Qdrant

> **Lưu ý:** Thư mục `data/chunks/` không được commit vào repo (có thể chứa dữ liệu bản quyền SGK). Liên hệ nhóm dự án để lấy file hoặc chạy lại pipeline xử lý từ nguồn gốc.

Khi đã có file JSONL trong `data/chunks/`, nạp vào Qdrant bằng lệnh sau (services phải đang chạy):

Nạp SGK / math chunks:

```bash
docker compose exec backend python -m backend.scripts.ingest_qdrant --input data/chunks/theory_chunks.jsonl
```

Nạp dictionary:

```bash
docker compose exec backend python -m backend.scripts.ingest_dict_combined
```

Kiểm tra mà không ghi vào Qdrant (dry-run):

```bash
docker compose exec backend python -m backend.scripts.ingest_dict_combined --dry-run
```

## Biến môi trường chính

| Biến | Ý nghĩa |
|---|---|
| `GEMINI_API_KEY` | API key gọi Gemini |
| `AI_MODEL_URL` | Base URL của AI model server embedding/reranker |
| `AI_MODEL_API_KEY` | API key của model server |
| `EMBED_URL` | Endpoint embedding (mặc định dùng `AI_MODEL_URL`) |
| `RERANK_URL` | Endpoint rerank (mặc định dùng `AI_MODEL_URL`) |
| `QDRANT_URL` | URL kết nối Qdrant |
| `QDRANT_COLLECTION_MATH` | Collection RAG Toán |
| `QDRANT_COLLECTION_DICT` | Collection từ điển |
| `VECTOR_SCORE_THRESHOLD` | Ngưỡng vector search |
| `RERANK_SCORE_THRESHOLD` | Ngưỡng rerank math |
| `RERANK_DICT_THRESHOLD` | Ngưỡng rerank dictionary |
| `REDIS_PASSWORD` | Mật khẩu Redis (bắt buộc) |
| `REDIS_*` | Cache và rate limit |
| `SUPABASE_URL` | URL project Supabase |
| `SUPABASE_PUBLISHABLE_KEY` | Key public (backend + frontend build) |
| `SUPABASE_SECRET_KEY` | Key bí mật (backend only) |
| `COMPACT_THRESHOLD` | Số messages để auto-compact |

Xem đầy đủ tại [.env.example](.env.example) và [frontend/.env.local.example](frontend/.env.local.example).

## Cấu trúc thư mục

```text
edu-chatbot/
├── backend/
│   ├── main.py
│   ├── routers/
│   │   ├── chat_v2.py          # endpoint chat SSE chính
│   │   ├── conversations.py    # conversation CRUD
│   │   ├── history.py          # saved vocab
│   │   ├── solver.py           # SymPy expression solver
│   │   └── teacher.py          # giáo viên / lesson plan
│   ├── services/
│   │   ├── orchestrator.py     # classify và điều phối query
│   │   ├── vector_search.py    # embedding -> Qdrant -> rerank
│   │   ├── dictionary_search.py
│   │   ├── gemini.py
│   │   ├── compactor.py        # auto-compact lịch sử hội thoại dài
│   │   ├── content_safety.py
│   │   ├── intent_detector.py
│   │   ├── math_rules.py
│   │   ├── rate_limiter.py
│   │   └── supabase_client.py
│   └── scripts/
│       ├── ingest_qdrant.py        # nạp SGK chunks
│       └── ingest_dict_combined.py # nạp từ điển
├── frontend/
│   ├── app/                    # Next.js App Router
│   ├── components/             # React components
│   ├── lib/                    # API clients, Supabase helpers
│   └── .env.local.example      # template env frontend
├── supabase/
│   └── migrations/             # 001–005 SQL migrations
├── data/
│   ├── chunks/                 # JSONL chunks (không commit)
│   └── raw/                    # nguồn PDF/Markdown (không commit)
├── .env.example
├── docker-compose.yml
└── requirements.txt
```
