"""Read side of lead_memory.

Read once, before the call starts. The block goes verbatim into the system
prompt. Nothing here is ever called mid-call, and nothing here is exposed
over HTTP - `lead_memory` has no API route by design.
"""
import logging

from app.db import db

log = logging.getLogger(__name__)

MAX_BLOCK_TOKENS = 1200


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free estimate. ~4 characters per token."""
    return max(1, (len(text) + 3) // 4)


async def read_memory_block(lead_id: str) -> str | None:
    """The verbatim memory block for the prompt, or None when there is none.

    Callers must omit the segment entirely on None - never substitute a
    placeholder, which would teach the model that empty memory is a fact.
    """
    doc = await db.lead_memory.find_one({"lead_id": lead_id})
    if not doc:
        return None
    block = (doc.get("memory_block") or "").strip()
    if not block:
        return None
    if estimate_tokens(block) > MAX_BLOCK_TOKENS:
        log.warning(
            "lead_memory for %s exceeds the %d token cap (v%s); using it anyway "
            "rather than truncating - the compactor should merge on the next pass",
            lead_id, MAX_BLOCK_TOKENS, doc.get("version"),
        )
    return block


async def read_memory_doc(lead_id: str) -> dict | None:
    """Full document, for the compactor only."""
    return await db.lead_memory.find_one({"lead_id": lead_id})
