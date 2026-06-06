# Edu Chatbot RAG

Chatbot giao duc ho tro hoc sinh vung cao / dan toc thieu so hoc va hoi dap kien thuc Toan bang tieng Viet don gian, co bo sung tra cuu tu dien Viet - Tay/Nung khi co du lieu phu hop.

Project tap trung vao hai muc tieu:

- Xay dung ung dung AI co kha nang hoi dap hoc tap bang RAG, Rule Engine va LLM fallback.
- Phan tich, kiem soat rui ro AI theo 5 truc cua mon **Tu duy tri tue nhan tao**: Reliability, Bias/Fairness, Robustness, Social Impact, Explainability.

## Tinh nang chinh

- Chat hoc sinh qua giao dien Next.js voi SSE streaming.
- Backend FastAPI dieu phoi cau hoi qua `orchestrator`.
- Rule Engine cho cac bai Toan co quy tac: phep tinh, chu vi, dien tich, doi don vi, phan tram...
- RAG voi Qdrant cho noi dung SGK / knowledge chunks.
- Vietnamese embedding va reranker thong qua AI model server rieng.
- Gemini fallback de dien dat cau tra loi tu nhien.
- Dictionary search Viet - Tay/Nung va Tay/Nung - Viet.
- Content safety, prompt-injection detection, rate limit.
- Supabase Auth va luu lich su hoi thoai.
- Redis cache cho Gemini response va rate limit.
- Auto-compact lich su hoi thoai dai.

## Tech stack

| Layer | Cong nghe |
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

## Kien truc xu ly chat

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

Diem quan trong: LLM khong duoc dung mot minh. He thong chen cac lop kiem soat nhu Rule Engine, RAG, reranker, content safety va metadata nguon de giam hallucination va tang kha nang kiem chung.

## 5 truc AI Ethics

| Truc | Rui ro | Co che trong project |
|---|---|---|
| Reliability | LLM hallucination, tinh sai, tra loi khong nhat quan | RAG, reranker, Rule Engine, Redis cache co history-aware key |
| Bias/Fairness | Thien vi ngon ngu/vung mien, du lieu Tay/Nung it | Dictionary search rieng, khong de LLM tu bia tu Tay/Nung, can human review |
| Robustness | Prompt injection, typo, input ngan/nhieu, OCR/Voice sai | Content safety, orchestrator, hoi lai khi mo ho, Voice/OCR la huong phat trien can xac nhan text |
| Social Impact | Hoc sinh phu thuoc AI, du lieu tre em nhay cam | Giai tung buoc, khong khuyen khich chep bai, han che du lieu ca nhan |
| Explainability | Hoc sinh khong hieu loi giai, giao vien kho kiem chung | Giai tung buoc, context RAG, metadata nguon, vocab table |

Tai lieu huong dan test 5 truc: [docs/ai_ethics_5_axes_test_guide.md](docs/ai_ethics_5_axes_test_guide.md)

## Chay nhanh voi Docker Compose

### 1. Tao file moi truong

```bash
cp .env.example .env
```

Dien cac bien bat buoc trong `.env`:

```env
GEMINI_API_KEY=
AI_MODEL_URL=https://ai-model.ndk.id.vn
AI_MODEL_API_KEY=
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SECRET_KEY=
REDIS_PASSWORD=
```

### 2. Khoi dong services

```bash
docker compose up -d --build
```

Sau khi chay:

- Frontend: `http://localhost:3000`
- Qdrant dashboard: `http://localhost:6333/dashboard`
- Backend API: chay noi bo trong Docker network tai `http://backend:8000`

Mac dinh `docker-compose.yml` khong expose port backend `8000` ra host. Neu can xem Swagger `http://localhost:8000/docs`, them mapping sau vao service `backend`:

```yaml
ports:
  - "8000:8000"
```

roi chay lai:

```bash
docker compose up -d --build backend
```

## Nap du lieu vao Qdrant

Data chunks nam trong `data/chunks/` va duoc mount vao container backend qua `./data:/app/data`.

Nap SGK / math chunks:

```bash
docker compose exec backend python -m backend.scripts.ingest_qdrant
```

Nap dictionary:

```bash
docker compose exec backend python -m backend.scripts.ingest_dict
```

Hoac voi dictionary combined neu dang dung pipeline moi:

```bash
docker compose exec backend python -m backend.scripts.ingest_dict_combined
```

Luu y: du lieu goc / SGK / PDF tu dien khong nen commit neu co rang buoc ban quyen.

## Bien moi truong chinh

| Bien | Y nghia |
|---|---|
| `GEMINI_API_KEY` | API key goi Gemini |
| `AI_MODEL_URL` | Base URL cua model server embedding/reranker |
| `AI_MODEL_API_KEY` | API key cua model server |
| `EMBED_URL` | Endpoint embedding |
| `RERANK_URL` | Endpoint rerank |
| `QDRANT_HOST`, `QDRANT_PORT` | Ket noi Qdrant |
| `QDRANT_COLLECTION_MATH` | Collection RAG Toan |
| `QDRANT_COLLECTION_DICT` | Collection tu dien |
| `VECTOR_SCORE_THRESHOLD` | Nguong vector search |
| `RERANK_SCORE_THRESHOLD` | Nguong rerank math |
| `RERANK_DICT_THRESHOLD` | Nguong rerank dictionary |
| `REDIS_*` | Cache va rate limit |
| `SUPABASE_*` | Auth, user, conversations, messages |
| `COMPACT_THRESHOLD` | So messages de auto-compact |

Xem day du tai [.env.example](.env.example).

## Cau truc thu muc

```text
edu-chatbot/
├── backend/
│   ├── main.py
│   ├── routers/
│   │   ├── chat_v2.py          # endpoint chat SSE chinh
│   │   ├── conversations.py    # conversation CRUD
│   │   ├── history.py          # legacy history / saved vocab
│   │   ├── solver.py           # solver endpoint
│   │   └── teacher.py          # giao vien / lesson plan
│   ├── services/
│   │   ├── orchestrator.py     # classify va dieu phoi query
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
├── docs/
├── supabase/
├── docker-compose.yml
└── requirements.txt
```

## Test nhanh

Chay unit tests hien co:

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Test search bang CLI:

```bash
python test_search.py
python test_dict_search.py --query "học" --dir vi_to_tay_nung
```

Smoke test nen dung truoc demo:

1. `chu vi hình chữ nhật dài 5cm rộng 3cm`
2. `chu vi hình chữ nhật là gì?`
3. `dịch từ học sang tiếng Tày`
4. `Ignore all previous instructions...`

## Luu y van hanh

- Khong nen toi uu runtime sat gio demo neu chua co log/metric ro rang.
- Model server embedding/reranker co the full CPU neu traffic lap, top_k qua cao, hoac co loi retry/loop. Khi debug, xem backend logs va model server request count truoc khi sua code.
- Redis cache Gemini da phan biet `history` bang hash ngan de tranh lay nham cache giua cac hoi thoai khac nhau.
- Voice va OCR hien nen trinh bay la huong phat trien / test mo phong neu chua co demo on dinh.

## Tai lieu lien quan

- [Huong dan test 5 truc AI Ethics](docs/ai_ethics_5_axes_test_guide.md)
- `docs/presentation_speaker_script.md` neu can script thuyet trinh local.
