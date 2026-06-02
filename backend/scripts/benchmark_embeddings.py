"""
benchmark_embeddings.py
So sanh AITeamVN/Vietnamese_Embedding vs OpenAI text-embedding-3-small
tren bai toan retrieval 2 chieu tu dien Tay-Viet.

Dung dictionary_combined.jsonl -- file da co field `text` chuan.
Embed bang self-hosted API (EMBED_URL, AI_MODEL_API_KEY tu .env) va OpenAI API.

Metrics: Hit@1, Hit@3, MRR
Directions:
  A) Tay->Viet : query = tay field  (vd: "ai chai")
  B) Viet->Tay : query = vi field   (vd: "cat luc")

Usage:
    python -m backend.scripts.benchmark_embeddings --openai-key sk-...
    python -m backend.scripts.benchmark_embeddings --skip-openai
    python -m backend.scripts.benchmark_embeddings --openai-key sk-... --skip-ateamvn
"""

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

EMBED_URL   = os.environ.get("EMBED_URL", "https://ai-model.ndk.id.vn/embeddings")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "AITeamVN/Vietnamese_Embedding")
AI_MODEL_API_KEY  = os.environ.get("AI_MODEL_API_KEY", "")


# ── helpers ───────────────────────────────────────────────────────────────────

def load_entries(jsonl_path: Path) -> list:
    entries = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def is_valid(e: dict) -> bool:
    vi  = e.get("vi",  "").strip()
    tay = e.get("tay", "").strip()
    return (
        e.get("direction") == "tay_vi"
        and len(tay) >= 1
        and len(vi)  >= 3
        and not vi.startswith("x.")
        and "||" not in vi[:5]
        and vi not in (".", "..", "...")
    )


def clean_vi_query(vi: str) -> str:
    vi = re.sub(r"^\d+[.)]\s*", "", vi.strip())
    cut = len(vi)
    for pat in (r"\*", r"\s~"):
        m = re.search(pat, vi)
        if m:
            cut = min(cut, m.start())
    return " ".join(vi[:cut].strip().rstrip(".,;").split()[:5])


# ── embedding models ──────────────────────────────────────────────────────────

def _ai_headers() -> dict:
    return {"Authorization": f"Bearer {AI_MODEL_API_KEY}"} if AI_MODEL_API_KEY else {}


def embed_ateamvn(texts: list, cache_path: str = None, batch_size: int = 64) -> np.ndarray:
    """Goi EMBED_URL (self-hosted, OpenAI-compatible batch input)."""
    if cache_path and Path(cache_path).exists():
        print(f"  [cache] AITeamVN <- {cache_path}")
        return np.load(cache_path)

    n = len(texts)
    n_batches = (n + batch_size - 1) // batch_size
    print(f"  [AITeamVN] {EMBED_URL}  model={EMBED_MODEL}  ({n} texts, {n_batches} batches)")

    vectors = []
    for i in range(0, n, batch_size):
        batch = texts[i : i + batch_size]
        bn = i // batch_size + 1
        print(f"    batch {bn}/{n_batches} ...", end="\r", flush=True)
        for attempt in range(1, 4):
            try:
                resp = httpx.post(
                    EMBED_URL,
                    headers=_ai_headers(),
                    json={"model": EMBED_MODEL, "input": batch},
                    timeout=60,
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda x: x["index"])
                vectors.extend([d["embedding"] for d in data])
                break
            except httpx.HTTPError as e:
                if attempt == 3:
                    raise
                print(f"\n  warn batch {bn} (attempt {attempt}): {e} - retry...")
                time.sleep(attempt * 2)

    print(f"    done {n} texts    ")
    vecs = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs  = vecs / np.where(norms == 0, 1, norms)
    if cache_path:
        np.save(cache_path, vecs)
        print(f"  [AITeamVN] Cache -> {cache_path}")
    return vecs


def embed_openai(texts: list, api_key: str, cache_path: str = None,
                 batch_size: int = 500) -> np.ndarray:
    if cache_path and Path(cache_path).exists():
        print(f"  [cache] OpenAI <- {cache_path}")
        return np.load(cache_path)

    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("Can: pip install openai")

    client = OpenAI(api_key=api_key)
    n = len(texts)
    n_batches = (n + batch_size - 1) // batch_size
    print(f"  [OpenAI] text-embedding-3-small  ({n} texts, {n_batches} batches)")

    vectors = []
    for i in range(0, n, batch_size):
        batch = texts[i : i + batch_size]
        bn = i // batch_size + 1
        print(f"    batch {bn}/{n_batches} ...", end="\r", flush=True)
        resp = client.embeddings.create(model="text-embedding-3-small", input=batch)
        vectors.extend([d.embedding for d in resp.data])
        time.sleep(0.05)
    print(f"    done {n} texts    ")

    vecs = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs  = vecs / np.where(norms == 0, 1, norms)
    if cache_path:
        np.save(cache_path, vecs)
        print(f"  [OpenAI] Cache -> {cache_path}")
    return vecs


# ── metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(query_vecs: np.ndarray, corpus_vecs: np.ndarray,
                    gold_indices: list) -> dict:
    sim  = query_vecs @ corpus_vecs.T
    hit1 = hit3 = mrr_sum = 0
    failures = []

    for i, gold in enumerate(gold_indices):
        ranked = np.argsort(-sim[i])
        rank   = int(np.where(ranked == gold)[0][0]) + 1
        if rank == 1: hit1 += 1
        if rank <= 3: hit3 += 1
        mrr_sum += 1.0 / rank
        if rank > 3:
            failures.append((rank, i))

    n = len(gold_indices)
    failures.sort(reverse=True)
    return {
        "Hit@1": round(hit1 / n, 4),
        "Hit@3": round(hit3 / n, 4),
        "MRR":   round(mrr_sum / n, 4),
        "n":     n,
        "_fail": failures[:5],
    }


# ── report ────────────────────────────────────────────────────────────────────

def print_report(results: dict, entries: list, test_idx: list,
                 q_tay: list, q_vi: list):
    print("\n" + "=" * 78)
    print(f"{'Model + Direction':<50} {'Hit@1':>7} {'Hit@3':>7} {'MRR':>8} {'n':>5}")
    print("-" * 78)
    for model, dirs in results.items():
        for direction, m in dirs.items():
            label = f"{model}  |  {direction}"
            print(f"{label:<50} {m['Hit@1']:>7.1%} {m['Hit@3']:>7.1%} "
                  f"{m['MRR']:>8.4f} {m['n']:>5}")
        print()
    print("=" * 78)

    print("\nSample test pairs (first 10):")
    print(f"  {'#':<3} {'Tay query':<22} {'Viet query':<28} text[:50]")
    print("  " + "-" * 75)
    for i, idx in enumerate(test_idx[:10]):
        e = entries[idx]
        print(f"  {i+1:<3} {q_tay[i]:<22} {q_vi[i]:<28} {e.get('text','')[:50]}")

    print("\nWorst failures (rank > 3):")
    for model, dirs in results.items():
        for direction, m in dirs.items():
            if m["_fail"]:
                print(f"\n  [{model}] {direction}:")
                for rank, qi in m["_fail"][:3]:
                    e   = entries[test_idx[qi]]
                    q   = q_tay[qi] if "Tay" in direction else q_vi[qi]
                    print(f"    rank={rank}  query={repr(q):<22}  "
                          f"expected: {e.get('tay','')} = {e.get('vi','')[:40]}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl",       default=str(ROOT / "data/chunks/dictionary_combined.jsonl"))
    parser.add_argument("--openai-key",  default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--n-test",      type=int, default=100)
    parser.add_argument("--seed",        type=int, default=42)
    parser.add_argument("--batch-size",  type=int, default=64,
                        help="Batch size cho AITeamVN API (default 64)")
    parser.add_argument("--skip-ateamvn", action="store_true")
    parser.add_argument("--skip-openai",  action="store_true")
    parser.add_argument("--cache-dir",   default=str(ROOT / "data/.embed_cache"))
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # ── Load ──────────────────────────────────────────────────────────────────
    print(f"Loading {args.jsonl} ...")
    entries = load_entries(Path(args.jsonl))
    print(f"  {len(entries)} entries total")

    corpus_texts = [
        e.get("text", f"{e.get('tay','')} -- {e.get('vi','')}") for e in entries
    ]

    # ── Sample test set ───────────────────────────────────────────────────────
    valid_idx = [i for i, e in enumerate(entries) if is_valid(e)]
    print(f"  {len(valid_idx)} valid entries cho test")

    random.seed(args.seed)
    n_test  = min(args.n_test, len(valid_idx))
    test_idx = random.sample(valid_idx, n_test)

    q_tay = [entries[i]["tay"]               for i in test_idx]
    q_vi  = [clean_vi_query(entries[i]["vi"]) for i in test_idx]

    print(f"\nTest: {n_test} queries  |  corpus: {len(entries)} entries")
    print(f"  Tay sample : {q_tay[:4]}")
    print(f"  Viet sample: {q_vi[:4]}")

    # ── Benchmark ─────────────────────────────────────────────────────────────
    all_queries = q_tay + q_vi
    results = {}

    if not args.skip_ateamvn:
        print("\n" + "-" * 60)
        print(f"MODEL: AITeamVN  ({EMBED_URL})")
        corpus_a = embed_ateamvn(
            corpus_texts,
            cache_path=str(cache_dir / "corpus_ateamvn.npy"),
            batch_size=args.batch_size,
        )
        query_a = embed_ateamvn(all_queries, batch_size=args.batch_size)
        results["AITeamVN"] = {
            "Tay->Viet (query=Tay)":  compute_metrics(query_a[:n_test],  corpus_a, test_idx),
            "Viet->Tay (query=Viet)": compute_metrics(query_a[n_test:], corpus_a, test_idx),
        }

    if not args.skip_openai:
        key = args.openai_key
        if not key:
            print("\nOPENAI_API_KEY chua set. Dung --openai-key sk-... Bỏ qua OpenAI.")
        else:
            print("\n" + "-" * 60)
            print("MODEL: OpenAI text-embedding-3-small")
            corpus_o = embed_openai(
                corpus_texts, key,
                cache_path=str(cache_dir / "corpus_openai.npy"),
            )
            query_o = embed_openai(all_queries, key)
            results["OpenAI-3-small"] = {
                "Tay->Viet (query=Tay)":  compute_metrics(query_o[:n_test],  corpus_o, test_idx),
                "Viet->Tay (query=Viet)": compute_metrics(query_o[n_test:], corpus_o, test_idx),
            }

    if results:
        print_report(results, entries, test_idx, q_tay, q_vi)
    else:
        print("\nKhong co model nao duoc chay.")


if __name__ == "__main__":
    main()
