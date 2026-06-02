#!/usr/bin/env python3
"""
Test nhanh dictionary search → collection edu_dictionary.

Cách dùng:
    python test_dict_search.py
    python test_dict_search.py --query "chu vi" --dir vi_to_tay_nung
    python test_dict_search.py --query "slíp" --dir tay_to_vi
"""
import argparse
import asyncio
import json
from dotenv import load_dotenv

load_dotenv()

from backend.services.dictionary_search import search_dictionary  # noqa: E402


async def main(query: str, direction: str) -> None:
    print(f"\n{'='*60}")
    print(f"Query     : {query!r}")
    print(f"Direction : {direction}")
    print(f"{'='*60}")

    result = await search_dictionary(query, direction=direction, top_k=10)

    if not result:
        print("⛔  search_dictionary trả None")
        return

    print(f"Status    : {result['retrieval_status']}")
    print(f"VecScore  : {result.get('top_vector_score', 0):.4f}")
    print(f"RerankScore: {result.get('top_rerank_score', 0):.4f}")
    print(f"Contexts  : {len(result.get('context', []))}")

    for i, ctx in enumerate(result.get("context", []), 1):
        print(f"\n--- Context {i} ---")
        print(f"  direction : {ctx.get('direction')}")
        print(f"  vi        : {ctx.get('vi')}")
        print(f"  tay       : {ctx.get('tay')}")
        print(f"  nung      : {ctx.get('nung')}")
        print(f"  content   : {(ctx.get('content') or '')[:120]}")
        print(f"  rerank    : {ctx.get('rerank_score', 0):.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="chu vi")
    parser.add_argument("--dir", default="vi_to_tay_nung",
                        choices=["vi_to_tay_nung", "tay_to_vi", "both"])
    args = parser.parse_args()

    asyncio.run(main(args.query, args.dir))
