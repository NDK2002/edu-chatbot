import asyncio
import argparse
import os
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_USERNAME = os.getenv("REDIS_USERNAME", "")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

CACHE_PREFIXES = {
    "gemini": "gemini:*",
    "qdrant": "qdrant:*",
}

_redis = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        if REDIS_USERNAME and REDIS_PASSWORD:
            url = f"redis://{REDIS_USERNAME}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}"
        else:
            url = f"redis://{REDIS_HOST}:{REDIS_PORT}"
        _redis = await aioredis.from_url(url, decode_responses=False)
    return _redis


async def _delete_by_pattern(r: aioredis.Redis, pattern: str) -> int:
    keys = await r.keys(pattern)
    if keys:
        await r.delete(*keys)
    return len(keys)


async def clear_cache(target: str = "all") -> dict[str, int]:
    """
    Xóa Redis cache theo target:
    - "all"    : toàn bộ key trong DB
    - "gemini" : chỉ key gemini:*
    - "qdrant" : chỉ key qdrant:*
    Trả về dict {prefix: số key đã xóa}.
    """
    r = await _get_redis()
    results: dict[str, int] = {}

    if target == "all":
        for name, pattern in CACHE_PREFIXES.items():
            results[name] = await _delete_by_pattern(r, pattern)
    elif target in CACHE_PREFIXES:
        pattern = CACHE_PREFIXES[target]
        results[target] = await _delete_by_pattern(r, pattern)
    else:
        raise ValueError(f"Target không hợp lệ: '{target}'. Chọn: all, {', '.join(CACHE_PREFIXES)}")

    return results


async def get_cache_stats() -> dict[str, int]:
    """Đếm số key hiện tại theo từng prefix."""
    r = await _get_redis()
    stats: dict[str, int] = {}
    for name, pattern in CACHE_PREFIXES.items():
        keys = await r.keys(pattern)
        stats[name] = len(keys)
    return stats


async def main():
    parser = argparse.ArgumentParser(description="Quản lý Redis cache cho edu-chatbot")
    subparsers = parser.add_subparsers(dest="command")

    clear_cmd = subparsers.add_parser("clear", help="Xóa cache")
    clear_cmd.add_argument(
        "--target",
        choices=["all"] + list(CACHE_PREFIXES.keys()),
        default="all",
        help="Nhóm cache cần xóa (default: all)",
    )

    subparsers.add_parser("stats", help="Xem số lượng key hiện tại")

    args = parser.parse_args()

    if args.command == "clear":
        results = await clear_cache(args.target)
        total = sum(results.values())
        for name, count in results.items():
            print(f"  [{name}] đã xóa {count} key")
        print(f"Tổng: {total} key đã xóa.")

    elif args.command == "stats":
        stats = await get_cache_stats()
        total = sum(stats.values())
        for name, count in stats.items():
            print(f"  [{name}] {count} key")
        print(f"Tổng: {total} key.")

    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
