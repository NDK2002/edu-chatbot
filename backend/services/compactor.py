"""
Auto-compact service: tóm tắt conversation khi đủ ngưỡng messages.
Chạy bất đồng bộ (asyncio.create_task), không block SSE stream.
"""

import logging
import os

from backend.services.gemini import ask_gemini
from backend.services.supabase_client import (
    count_uncompacted,
    get_all_uncompacted,
    mark_messages_compacted,
    set_compact_summary,
)

log = logging.getLogger(__name__)

COMPACT_THRESHOLD = int(os.getenv("COMPACT_THRESHOLD", "20"))
COMPACT_KEEP_LAST = int(os.getenv("COMPACT_KEEP_LAST", "5"))


async def should_compact(conversation_id: str) -> bool:
    count = await count_uncompacted(conversation_id)
    return count >= COMPACT_THRESHOLD


async def compact_conversation(conversation_id: str) -> None:
    try:
        all_messages = await get_all_uncompacted(conversation_id)
        if len(all_messages) <= COMPACT_KEEP_LAST:
            return

        keep_ids = {m["id"] for m in all_messages[-COMPACT_KEEP_LAST:]}
        old_messages = [m for m in all_messages if m["id"] not in keep_ids]
        if not old_messages:
            return

        conv_text = "\n".join(
            f"{'Học sinh' if m['role'] == 'user' else 'Trợ lý'}: {m['content'][:300]}"
            for m in old_messages
        )

        prompt = (
            "Tóm tắt ngắn gọn cuộc hội thoại học tập sau đây trong 150-200 từ.\n"
            "Giữ lại: các khái niệm đã học, bài toán đã giải, từ vựng song ngữ quan trọng.\n"
            "Bỏ qua: lời chào hỏi, câu xã giao.\n"
            "Trả lời bằng tiếng Việt.\n\n"
            f"{conv_text}"
        )

        summary = await ask_gemini(
            prompt=prompt,
            context="",
            grade=0,
            language="vi",
            role="student",
        )
        if not summary:
            log.warning("[COMPACTOR] Empty summary for conv %s", conversation_id)
            return

        old_ids = [m["id"] for m in old_messages]
        await set_compact_summary(conversation_id, summary)
        await mark_messages_compacted(old_ids)

        log.info(
            "[COMPACTOR] Compacted conv %s: %d messages → summary (%d chars)",
            conversation_id, len(old_ids), len(summary),
        )
    except Exception as exc:
        log.warning("[COMPACTOR] compact_conversation failed for %s: %s", conversation_id, exc)
