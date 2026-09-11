"""Close out a call and run the post-call chain.

Called by both runners. Writes the terminal state of the call document, then
schedules analysis, memory compaction and the follow-up draft as one background
task so the HTTP request that ended the call does not wait on three model calls.
"""
import asyncio
import logging

from app.analysis import analyzer, metrics
from app.db import db, utcnow
from app.memory import compactor
from app.outbound import composer

log = logging.getLogger(__name__)


async def finalize_call(
    call_id: str,
    duration_s: int,
    escalated: bool,
    memory_candidates: list[dict] | None = None,
    status: str = "completed",
) -> None:
    """Write the call doc, then hand off to the post-call chain.

    `status="failed"` is for a call that never became a conversation - no
    answer, busy, a dial that errored. Those are not graded and must not mark
    the lead as contacted: nobody spoke to them, and the next person to open
    the queue needs to see the lead still waiting.
    """
    call = await db.calls.find_one({"call_id": call_id})
    if call is None:
        log.error("finalize_call: no such call %s", call_id)
        return

    transcript = call.get("transcript", [])
    connected = status == "completed" and bool(transcript)

    await db.calls.update_one(
        {"call_id": call_id},
        {
            "$set": {
                "status": status,
                "ended_at": utcnow(),
                "duration_s": duration_s,
                "metrics": metrics.compute(transcript),
                "analysis.status": "pending" if connected else "failed",
            }
        },
    )

    if not connected:
        # Nothing was said, so there is nothing to grade. Put the lead back.
        await db.leads.update_one(
            {"lead_id": call["lead_id"], "lead_status": "Calling"},
            {"$set": {"lead_status": "Queued"}},
        )
        log.info("%s did not connect (%s) - lead returned to the queue", call_id, status)
        return

    # A call that ended without escalating still needs its lead taken off
    # "Calling"; the analysis gate below sets the real status a moment later.
    if not escalated:
        await db.leads.update_one(
            {"lead_id": call["lead_id"], "lead_status": "Calling"},
            {"$set": {"lead_status": "Contacted"}},
        )

    asyncio.create_task(run_post_call(call_id, memory_candidates or []))


async def run_post_call(call_id: str, memory_candidates: list[dict]) -> None:
    """LLM-2a, LLM-2b, the status gate, LLM-2c, then LLM-3."""
    call = await db.calls.find_one({"call_id": call_id})
    lead = await db.leads.find_one({"lead_id": call["lead_id"]})

    try:
        result = await analyzer.analyze(call, lead)
    except Exception:
        log.exception("analysis failed for %s", call_id)
        await db.calls.update_one(
            {"call_id": call_id}, {"$set": {"analysis.status": "failed"}}
        )
        return

    await db.calls.update_one(
        {"call_id": call_id},
        {
            "$set": {
                "analysis.status": "done",
                "analysis.deployment": result["deployment"],
                "analysis.analyzed_at": utcnow(),
                "analysis.conversion": result["conversion"],
                "analysis.safety": result["safety"],
            }
        },
    )

    await apply_gate(lead, result)

    try:
        await compactor.compact(
            lead["lead_id"], call_id, memory_candidates, call.get("transcript", [])
        )
    except Exception:
        log.exception("memory compaction failed for %s", call_id)

    try:
        await composer.draft_followup(call_id)
    except Exception:
        log.exception("follow-up draft failed for %s", call_id)


async def apply_gate(lead: dict, result: dict) -> None:
    """The gate rules, applied literally.

    A safety failure overrides the conversion track's proposal outright. There
    is no combined score anywhere in this function, and there must never be one.
    """
    conversion = result["conversion"]
    safety = result["safety"]

    if safety["verdict"] == "fail":
        status = "Escalated"
    else:
        status = conversion.get("proposed_status")

    update: dict = {"last_contact_date": utcnow()}
    if status:
        update["lead_status"] = status
    if not lead.get("first_contact_date"):
        update["first_contact_date"] = utcnow()

    # Apply what the call actually captured back onto the lead.
    for field in conversion.get("fields_captured", []):
        value = lead.get(field)
        if value not in (None, "", [], 0):
            update.setdefault(field, value)

    await db.leads.update_one({"lead_id": lead["lead_id"]}, {"$set": update})
    log.info(
        "gate: %s -> %s (safety=%s, conversion=%.2f)",
        lead["lead_id"], status or lead["lead_status"],
        safety["verdict"], conversion.get("track_score", 0.0),
    )
