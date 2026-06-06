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
| Embedding | `AITeamVN/Vietnamese_Embedding` qua remote AI model server |
| Reranker | `BAAI/bge-reranker-v2-m3` qua remote AI model server |
| LLM | Google Gemini 2.5 Flash / Flash Lite fallback |
| Cache / rate limit | Redis |
| Auth / DB | Supabase |
| Math | Custom Rule Engine + SymPy |
| Deploy local | Docker Compose |

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

## Chạy nhanh với Docker Compose

### 1. Tạo file môi trường

```bash
cp .env.example .env
```

Điền các biến bắt buộc trong `.env`:

```env
GEMINI_API_KEY=
AI_MODEL_URL=https://ai-model.ndk.id.vn
AI_MODEL_API_KEY=
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SECRET_KEY=
REDIS_PASSWORD=
```

### 2. Khởi động services

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

## Nạp dữ liệu vào Qdrant

Data chunks nằm trong `data/chunks/` và được mount vào container backend qua `./data:/app/data`.

Nạp SGK / math chunks:

```bash
docker compose exec backend python -m backend.scripts.ingest_qdrant
```

Nạp dictionary:

```bash
docker compose exec backend python -m backend.scripts.ingest_dict_combined
```

Lưu ý: dữ liệu gốc / SGK / PDF từ điển không nên commit nếu có ràng buộc bản quyền.

## Biến môi trường chính

| Biến | Ý nghĩa |
|---|---|
| `GEMINI_API_KEY` | API key gọi Gemini |
| `AI_MODEL_URL` | Base URL của model server embedding/reranker |
| `AI_MODEL_API_KEY` | API key của model server |
| `EMBED_URL` | Endpoint embedding |
| `RERANK_URL` | Endpoint rerank |
| `QDRANT_HOST`, `QDRANT_PORT` | Kết nối Qdrant |
| `QDRANT_COLLECTION_MATH` | Collection RAG Toán |
| `QDRANT_COLLECTION_DICT` | Collection từ điển |
| `VECTOR_SCORE_THRESHOLD` | Ngưỡng vector search |
| `RERANK_SCORE_THRESHOLD` | Ngưỡng rerank math |
| `RERANK_DICT_THRESHOLD` | Ngưỡng rerank dictionary |
| `REDIS_*` | Cache và rate limit |
| `SUPABASE_*` | Auth, user, conversations, messages |
| `COMPACT_THRESHOLD` | Số messages để auto-compact |

Xem đầy đủ tại [.env.example](.env.example).

## Cấu trúc thư mục

```text
edu-chatbot/
├── backend/
│   ├── main.py
│   ├── routers/
│   │   ├── chat_v2.py          # endpoint chat SSE chính
│   │   ├── conversations.py    # conversation CRUD
│   │   ├── history.py          # legacy history / saved vocab
│   │   ├── solver.py           # solver endpoint
│   │   └── teacher.py          # giáo viên / lesson plan
│   ├── services/
│   │   ├── orchestrator.py     # classify và điều phối query
│   │   ├── vector_search.py    # embedding -> Qdrant -> rerank
│   │   ├── dictionary_search.py
│   │   ├── gemini.py
│   │   ├── content_safety.py
│   │   ├── intent_detector.py
│   │   ├── math_rules.py
│   │   └── supabase_client.py
│   └── scripts/
│       ├── ingest_qdrant.py
│       ├── ingest_dict.py
│       └── ingest_dict_combined.py
├── frontend/
│   ├── app/
│   ├── components/
│   └── lib/
├── data/
│   ├── chunks/
│   └── raw/
├── supabase/
├── docker-compose.yml
└── requirements.txt
```
