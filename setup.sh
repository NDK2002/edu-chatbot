#!/bin/bash
# setup.sh — Run only once after git pull on server
# Usage: bash setup.sh

set -e  # stop immediately if there is an error

echo "=== 1. Create data directory ==="
mkdir -p data/raw data/chunks

echo "=== 2. Check .env ==="
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠ No .env — copied from .env.example"
    echo "  → Mở .env, điền GEMINI_API_KEY rồi chạy lại script này"
    exit 1
fi

if grep -q "your_gemini_api_key_here" .env; then
    echo "⚠ GEMINI_API_KEY not filled in .env"
    exit 1
fi

echo "=== 3. Start Qdrant + Redis first ==="
docker compose up -d qdrant redis
echo "   Waiting for Qdrant to be ready..."
sleep 5

echo "=== 4. Install Python dependencies ==="
pip install -r requirements.txt -q

echo "=== 5. Crawl textbook (Math grade 3-5) ==="
python -m backend.scripts.crawl_textbook \
    --grades 3 4 5 \
    --subjects toan \
    --output data/chunks/textbook_chunks.jsonl

echo "=== 6. Crawl H'Mông dictionary ==="
python -m backend.scripts.crawl_hmong_dict \
    --all \
    --output data/chunks

echo "=== 7. Ingest textbook into Qdrant ==="
python -m backend.scripts.ingest_qdrant \
    --input data/chunks/textbook_chunks.jsonl

echo "=== 8. Ingest H'Mông dictionary into Qdrant ==="
python -m backend.scripts.ingest_qdrant \
    --input data/chunks/hmong_viet_chunks.jsonl

echo "=== 9. Start full stack ==="
docker compose up -d

echo ""
echo "✅ Setup completed!"
echo "   Backend API : http://localhost:8000/docs"
echo "   Qdrant UI   : http://localhost:6333/dashboard"
