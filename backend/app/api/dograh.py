"""The inbound half of the Dograh seam: what the orchestrator calls on us.

Two kinds of traffic arrive here, and they are the reason this app still has
opinions about a call it no longer runs:

  POST /api/dograh/tools/{name}   one tool call from the live agent
  POST /api/dograh/webhook        the run finished; grade it

Dograh's HTTP API tools are configured to point at the tool endpoint, one tool
per node attachment (https://docs.dograh.com/voice-agent/tools/http-api). The
important consequence is that **the guardrail still runs on this side of the
wire**: Dograh proposes a tool call, and `agent/turn.py::run_tool` decides
whether it is allowed before anything touches the database. Moving the
conversation to an orchestrator did not move the rules.

The agent's private memory collection is never read or returned by any
endpoint here - that rule is enforced by a grep in test_invariants.py, which is
why it is not named in this file.
"""
from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.agent.tools import ToolContext
from app.config import settings
from app.db import db

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dograh", tags=["dograh"])

# Statuses a call can still be moved out of. Anything else has been graded
# already, and a webhook retry must not re-grade it - Dograh documents that
# retries may deliver the same payload more than once.
LIVE_STATUSES = ("ringing", "in_progress")


def _authenticate(secret: str | None) -> None:
    """Both endpoints are on the public internet and both write to the database.

    Dograh sends this as a custom header on the tool and webhook definitions.
    Without it, anyone who learns a call_id could book appointments on a real
    lead or close out a live call.
    """
    if not settings.dograh_shared_secret:
        raise HTTPException(503, "DOGRAH_SHARED_SECRET is not set")
    if not hmac.compare_digest(settings.dograh_shared_secret, secret or ""):
        log.warning("rejected an unauthenticated dograh request")
        raise HTTPException(403, "bad shared secret")


# ------------------------------------------------------------------ tool calls

async def _load_context(call_id: str) -> tuple[ToolContext, dict]:
    """Rebuild the agent's tool context for one call.

    Every tool call is a separate HTTP request, so the parts of the context
    that accumulate over a conversation - what has been presented, what the
    agent wants to remember - are carried on the call document rather than in
    memory. Losing them would let the agent present the same flat twice and
    would drop every `note_memory` on the floor.
    """
    call = await db.calls.find_one({"call_id": call_id})
    if call is None:
        raise HTTPException(404, f"no call {call_id}")

    lead = await db.leads.find_one({"lead_id": call["lead_id"]})
    if lead is None:
        raise HTTPException(404, f"no lead for {call_id}")

    from app.agent.context import match_properties

    ctx = ToolContext(
        call_id=call_id,
        lead=dict(lead),
        properties=await match_properties(lead),
        memory_candidates=list(call.get("memory_candidates") or []),
        presented=list(call.get("presented") or []),
        should_end=bool(call.get("should_end")),
        escalation_reason=call.get("escalation_reason"),
    )
    return ctx, call


async def _save_context(ctx: ToolContext) -> None:
    await db.calls.update_one(
        {"call_id": ctx.call_id},
        {
            "$set": {
                "memory_candidates": ctx.memory_candidates,
                "presented": ctx.presented,
                "should_end": ctx.should_end,
            }
        },
    )


@router.post("/tools/{name}")
async def call_tool(
    name: str,
    request: Request,
    x_dograh_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    """Run one tool the live agent asked for.

    The body is whatever the tool's parameters were declared as in Dograh,
    plus `broker_call_id`, which `initial_context` put there when the call was
    placed. The reply is a string, because that is what a conversational agent
    can actually say back.
    """
    _authenticate(x_dograh_secret)

    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(422, "expected a JSON object")

    call_id = str(body.pop("broker_call_id", "") or "")
    if not call_id:
        raise HTTPException(422, "broker_call_id is required")

    from app.agent.tools import TOOL_SCHEMAS

    known = {t["function"]["name"] for t in TOOL_SCHEMAS}
    if name not in known:
        raise HTTPException(404, f"no tool {name}")

    ctx, call = await _load_context(call_id)
    if call["status"] not in LIVE_STATUSES:
        raise HTTPException(409, f"call {call_id} is {call['status']}")

    from app.agent.turn import Tape, run_tool

    tape = Tape(call_id)
    tape.idx = len(call.get("transcript") or [])
    tape.elapsed_ms = _elapsed_ms(call)

    result = await run_tool(name, dict(body), ctx, tape)
    await _save_context(ctx)

    return {
        "result": result,
        "escalated": ctx.escalation_reason is not None,
        "end_call": ctx.should_end,
    }


def _elapsed_ms(call: dict) -> int:
    """Where the clock stands, from the transcript already written.

    Dograh owns the real clock now. This keeps `at_ms` monotonic across tool
    calls so `analysis/metrics.py` still reads a sane ordering.
    """
    transcript = call.get("transcript") or []
    return int(transcript[-1]["at_ms"]) if transcript else 0


# --------------------------------------------------------------------- webhook

@router.post("/webhook")
async def webhook(
    request: Request,
    x_dograh_secret: str | None = Header(default=None),
) -> dict[str, str]:
    """One finished run. Ingest the transcript, then grade it.

    Dograh sends this asynchronously after the run completes and expects a 2xx
    within 30 seconds, so this does the cheap part inline - write the
    transcript, close the row - and lets `finalize_call` fan out to the
    analyzer, the memory compactor and the composer as it always has.
    """
    _authenticate(x_dograh_secret)

    payload = await request.json()
    run_id = payload.get("workflow_run_id")

    # Dograh renders the payload template with Jinja, one scalar at a time, so
    # the flat keys are what actually arrive. The nested lookups are a fallback
    # for a template that was written to send whole objects.
    gathered = payload.get("gathered_context") or {}
    initial = payload.get("initial_context") or {}
    if not isinstance(gathered, dict):
        gathered = {}
    if not isinstance(initial, dict):
        initial = {}

    call_id = str(
        payload.get("broker_call_id")
        or initial.get("broker_call_id")
        or gathered.get("broker_call_id")
        or ""
    )
    call = None
    if call_id:
        call = await db.calls.find_one({"call_id": call_id})
    if call is None and run_id is not None:
        call = await db.calls.find_one({"dograh_run_id": int(run_id)})
    if call is None:
        log.warning("dograh webhook for an unknown run %s / %s", run_id, call_id)
        return {"status": "ignored"}

    call_id = call["call_id"]
    if call["status"] not in LIVE_STATUSES:
        # Retries may deliver the same payload more than once; grading twice
        # would rewrite an analysis that has already been read.
        log.info("dograh webhook for %s arrived again; already %s", call_id, call["status"])
        return {"status": "already-finalized"}

    duration_s = _duration_seconds(payload)
    recording_url = payload.get("recording_url")

    turns = await _ingest_transcript(call_id, payload.get("transcript_url") or "")

    # The detector is a backstop here, not the primary gate. Dograh owns turn
    # ordering now, so the guarantee this app can still make is about the
    # outcome: a call where the lead asked for something unlawful ends
    # escalated and is gated, whatever the workflow did in the moment.
    escalated, reason = _scan_for_escalation(turns)
    if escalated and not call.get("escalated"):
        log.info("post-call detector fired on %s (%s)", call_id, reason)

    from app.agent.finalize import finalize_call

    if recording_url:
        await db.calls.update_one(
            {"call_id": call_id}, {"$set": {"recording_url": recording_url}}
        )

    status = "completed" if turns else "failed"
    await finalize_call(
        call_id,
        duration_s=max(duration_s, 1) if turns else 0,
        escalated=escalated or bool(call.get("escalated")),
        memory_candidates=list(call.get("memory_candidates") or []),
        status=status,
    )
    log.info("dograh run %s finalized %s (%s turns, %ss)", run_id, call_id, len(turns), duration_s)
    return {"status": "ok"}


def _duration_seconds(payload: dict) -> int:
    """How long the call lasted, flat key first.

    Arrives as a string, because a Jinja-rendered template value always does.
    """
    raw = payload.get("call_duration_seconds")
    if raw is None:
        cost = payload.get("cost_info")
        raw = cost.get("call_duration_seconds") if isinstance(cost, dict) else None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return 0


async def _ingest_transcript(call_id: str, transcript_url: str) -> list[dict]:
    """Write Dograh's transcript into the call document.

    Tool calls were already recorded as they happened, so only the spoken
    turns come from here. They are rewritten wholesale rather than appended:
    Dograh's copy is authoritative for what was actually said.
    """
    from app.dograh.client import fetch_transcript

    raw = await fetch_transcript(transcript_url)
    turns: list[dict] = []
    for idx, entry in enumerate(raw):
        role = str(entry.get("role") or entry.get("speaker") or "").lower()
        text = (entry.get("text") or entry.get("content") or "").strip()
        if not text:
            continue
        turns.append(
            {
                "idx": idx,
                # Dograh speaks in assistant/user; the dashboards and the
                # rubrics have always spoken in agent/lead.
                "role": "agent" if role in ("assistant", "agent", "bot") else "lead",
                "text": text,
                "at_ms": int(entry.get("at_ms") or entry.get("start_ms") or idx * 3000),
            }
        )

    if turns:
        await db.calls.update_one(
            {"call_id": call_id}, {"$set": {"transcript": turns}}
        )
    return turns


def _scan_for_escalation(turns: list[dict]) -> tuple[bool, str | None]:
    from app.agent import escalation

    for turn in turns:
        if turn["role"] != "lead":
            continue
        reason = escalation.detect(turn["text"])
        if reason:
            return True, reason
    return False, None
