"""Call lifecycle routes."""
import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.db import db, next_id, utcnow
from app.models import StartCallRequest, StartCallResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calls", tags=["calls"])

# A call occupies the line from the moment it is created, ringing or not.
ACTIVE_STATUSES = ["ringing", "in_progress"]

NEW_CALL_DOC = {
    "direction": "outbound",
    "ended_at": None,
    "duration_s": None,
    "status": "in_progress",
    "transcript": [],
    "tool_calls": [],
    "escalated": False,
    "escalation_reason": None,
    "escalated_at": None,
    "metrics": {
        "agent_talk_ratio": 0.0,
        "avg_latency_ms": 0,
        "dead_air_events": 0,
        "turn_count": 0,
    },
    "analysis": {
        "status": "pending",
        "deployment": None,
        "analyzed_at": None,
        "conversion": None,
        "safety": None,
    },
    "recording_url": None,
    "dograh_run_id": None,
}


@router.post("/start", response_model=StartCallResponse)
async def start_call(body: StartCallRequest) -> StartCallResponse:
    lead = await db.leads.find_one({"lead_id": body.lead_id})
    if lead is None:
        raise HTTPException(404, f"No lead {body.lead_id}")

    active = await db.calls.find_one({"status": {"$in": ACTIVE_STATUSES}})
    if active is not None:
        raise HTTPException(
            409, f"Call {active['call_id']} is already in progress"
        )

    transport = settings.transport
    # A phone has to ring before it can be answered; a scripted call is under
    # way the moment the row exists.
    status = "ringing" if transport == "dograh" else "in_progress"

    call_id = await next_id("CL", db.calls, "call_id")
    await db.calls.insert_one(
        {**NEW_CALL_DOC, "call_id": call_id, "lead_id": lead["lead_id"],
         "transport": transport, "status": status, "started_at": utcnow()}
    )
    await db.leads.update_one(
        {"lead_id": lead["lead_id"]}, {"$set": {"lead_status": "Calling"}}
    )

    if transport == "dograh":
        await _dial(call_id, lead)
    else:
        from app.agent.mock_runner import run_mock_call

        asyncio.create_task(run_mock_call(call_id))

    log.info("started %s for %s (transport=%s)", call_id, lead["lead_id"], transport)
    return StartCallResponse(call_id=call_id, status=status)


async def _dial(call_id: str, lead: dict) -> None:
    """Hand the call to Dograh. Everything after this arrives as a tool call
    or a webhook.

    What Dograh gets is context, not instructions: who the lead is, what they
    are looking for, which properties match today, and their memory block if
    they have one. The workflow's own prompt decides what to do with it, and
    the tools it calls come back here - so the guardrail still runs on this
    side of the wire.

    An orchestrator refusal is not a failed conversation - nobody was called,
    so there is nothing to grade. The row is closed out and the lead goes back
    in the queue rather than sitting in `ringing` forever.
    """
    from zoneinfo import ZoneInfo

    from app.agent.context import format_properties, lead_digest, match_properties
    from app.agent.finalize import finalize_call
    from app.dograh.client import place_call
    from app.memory.reader import read_memory_block

    properties = await match_properties(lead)
    # The memory block is prose the agent reads, never a field Dograh stores.
    # It leaves this process only as part of the prompt context for one call.
    memory = await read_memory_block(lead["lead_id"]) or ""

    # A model asked to turn "day after tomorrow" into an ISO datetime with no
    # idea what day it is will invent one, and did: a viewing booked in 2023,
    # which then never appeared on the owner's dashboard because it had already
    # passed. Anchor it. IST because every lead and every property is in Gurugram.
    now_ist = utcnow().astimezone(ZoneInfo("Asia/Kolkata"))

    context = {
        "today": now_ist.strftime("%A, %d %B %Y"),
        "now_iso": now_ist.isoformat(timespec="seconds"),
        "timezone": "Asia/Kolkata",
        "lead_id": lead["lead_id"],
        "first_name": lead.get("first_name", ""),
        "last_name": lead.get("last_name", ""),
        "lead_type": lead.get("lead_type", ""),
        "lead_digest": lead_digest(lead),
        "matched_properties": format_properties(properties),
        "memory_block": memory,
    }

    try:
        run_id = await place_call(
            to=lead["phone"], call_id=call_id, context=context
        )
    except Exception as exc:
        log.exception("could not hand %s to dograh", call_id)
        await finalize_call(call_id, duration_s=0, escalated=False, status="failed")
        raise HTTPException(502, f"the orchestrator refused the call: {exc}") from exc

    await db.calls.update_one(
        {"call_id": call_id}, {"$set": {"dograh_run_id": run_id}}
    )


@router.get("/{call_id}")
async def get_call(call_id: str) -> dict:
    call = await db.calls.find_one({"call_id": call_id}, {"_id": 0})
    if call is None:
        raise HTTPException(404, f"No call {call_id}")
    lead = await db.leads.find_one(
        {"lead_id": call["lead_id"]},
        {"_id": 0, "first_name": 1, "last_name": 1, "lead_type": 1, "phone": 1},
    )
    call["lead"] = lead
    return call
