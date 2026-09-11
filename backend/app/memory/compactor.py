"""LLM-2c: rewrite the lead's memory block after a call.

The only writer of `lead_memory`. Runs after a call ends, never during one.

Hard cap is 1200 tokens. If the rewrite is over, re-run asking for a merge.
Never truncate - a block cut mid-sentence turns a constraint into its opposite.
On repeated failure keep the previous version and log.
"""
import json
import logging

from app.analysis.schemas import MEMORY_SCHEMA
from app.db import db, utcnow
from app.llm import azure_client
from app.memory.reader import MAX_BLOCK_TOKENS, estimate_tokens, read_memory_doc

log = logging.getLogger(__name__)

SYSTEM = """You maintain the private memory a voice agent carries between calls with
one person. You are rewriting the whole block from the previous block plus what
was learned on the latest call.

Write the block as short factual lines under a single header:

MEMORY (from N earlier calls)
- <one durable fact per line>

Rules.
- Durable facts only: preferences, constraints, why they rejected something,
  who else decides with them, how they like to be spoken to, commitments made,
  and sensitivities to avoid raising.
- Never record: anything about religion, caste, community, marital status, food
  habits or region of origin, even if the caller volunteered it. Never record
  payment details or anything said during an escalation.
- Merge duplicates. Drop anything the latest call contradicts. Prefer the newer
  statement when two facts conflict.
- No pleasantries, no call summary, no next steps, no dates unless the fact is
  a date the person committed to.
- Keep the whole block under 900 words. Shorter is better."""


def _header(calls: int) -> str:
    return f"MEMORY (from {calls} earlier call{'s' if calls != 1 else ''})"


def _with_header(block: str, calls: int) -> str:
    """Guarantee the block announces itself as memory.

    The block is dropped verbatim into the middle of the system prompt, between
    the escalation instructions and the property list. Without the header it
    reads as loose bullets belonging to whatever came before it, so this is
    enforced in code rather than left to the model to remember.
    """
    if not block:
        return block
    if block.lstrip().upper().startswith("MEMORY"):
        return block
    return f"{_header(calls)}\n{block}"


def _render_offline_block(prev: dict | None, candidates: list[dict], calls: int) -> str:
    lines = []
    seen: set[str] = set()
    if prev:
        for line in (prev.get("memory_block") or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("-") and stripped.lower() not in seen:
                seen.add(stripped.lower())
                lines.append(stripped)
    for cand in candidates:
        line = f"- {cand['text'].strip()}"
        if line.lower() not in seen:
            seen.add(line.lower())
            lines.append(line)
    if not lines:
        return ""
    return f"{_header(calls)}\n" + "\n".join(lines)


async def compact(lead_id: str, call_id: str, candidates: list[dict], transcript: list[dict]) -> None:
    prev = await read_memory_doc(lead_id)
    version = (prev.get("version", 0) if prev else 0) + 1

    if not azure_client.available():
        block = _render_offline_block(prev, candidates, version)
        entries = [dict(c, call_id=call_id) for c in candidates]
        if not block:
            log.info("nothing to remember for %s after %s", lead_id, call_id)
            return
        await _write(lead_id, version, block, (prev or {}).get("entries", []) + entries)
        return

    dialogue = "\n".join(
        f"[{t['idx']}] {t['role'].upper()}: {t['text']}"
        for t in sorted(transcript, key=lambda x: x["idx"])
    )
    noted = "\n".join(f"- ({c['kind']}) {c['text']}" for c in candidates) or "(none)"
    base_user = (
        f"PREVIOUS BLOCK\n{(prev or {}).get('memory_block') or '(none - this is the first call)'}\n\n"
        f"NOTED DURING THE LATEST CALL\n{noted}\n\n"
        f"LATEST CALL TRANSCRIPT\n{dialogue}"
    )

    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": base_user}]
    for attempt in range(2):
        raw = await azure_client.complete_json(
            "analyzer", messages, "lead_memory", MEMORY_SCHEMA, temperature=0
        )
        data = json.loads(raw)
        block = _with_header((data.get("memory_block") or "").strip(), version)
        tokens = estimate_tokens(block)
        if tokens <= MAX_BLOCK_TOKENS:
            entries = [
                {"kind": e["kind"], "text": e["text"], "call_id": call_id, "created_at": utcnow()}
                for e in data.get("entries", [])
            ]
            await _write(lead_id, version, block, entries)
            return
        log.warning(
            "memory block for %s is %d tokens, over the %d cap (attempt %d) - asking for a merge",
            lead_id, tokens, MAX_BLOCK_TOKENS, attempt + 1,
        )
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"That block is {tokens} tokens, over the {MAX_BLOCK_TOKENS} cap. "
                    "Merge related lines and drop the least useful facts. Do not "
                    "truncate a line mid-sentence. Return the full block again."
                ),
            }
        )

    log.error(
        "compactor could not get lead_memory for %s under the cap; keeping version %s",
        lead_id, (prev or {}).get("version", 0),
    )


async def _write(lead_id: str, version: int, block: str, entries: list[dict]) -> None:
    await db.lead_memory.update_one(
        {"lead_id": lead_id},
        {
            "$set": {
                "lead_id": lead_id,
                "version": version,
                "memory_block": block,
                "block_tokens": estimate_tokens(block),
                "entries": entries,
                "updated_at": utcnow(),
            }
        },
        upsert=True,
    )
    log.info("lead_memory %s -> v%d (%d tokens)", lead_id, version, estimate_tokens(block))
