"""Scripted call runner - nobody on the other end.

Routed to when the call transport is `mock`. The lead side is replayed from
seed/scripts/*.json one turn at a time, but everything on the agent side is
real: the same system prompt, the same detector, the same LLM-1 call, the same
guardrail and the same finalize path as a dialled call. Documents are written
exactly as the VoBiz runner writes them, so the broker dashboard streams a
scripted call and a real one identically.
"""
import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Any

from app.agent import escalation
from app.agent.context import build_system_prompt, match_properties
from app.agent.finalize import finalize_call
from app.agent.tools import ToolContext
from app.agent.turn import Tape, agent_reply, model_available, run_tool
from app.config import BACKEND_ROOT
from app.db import db, utcnow

log = logging.getLogger(__name__)

SCRIPTS_DIR = BACKEND_ROOT / "seed" / "scripts"
TURN_DELAY_S = 2.0


# --------------------------------------------------------------------- scripts

def load_scripts() -> list[dict]:
    scripts = []
    for path in sorted(SCRIPTS_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as fh:
            scripts.append(json.load(fh))
    return scripts


def pick_script(lead_id: str) -> dict:
    scripts = load_scripts()
    if not scripts:
        raise FileNotFoundError(f"no call scripts in {SCRIPTS_DIR}")
    for s in scripts:
        if lead_id in s.get("lead_ids", []):
            return s
    return next((s for s in scripts if s["name"] == "happy_path"), scripts[0])


# ------------------------------------------------------------------ agent turn

async def _agent_reply(
    messages: list[dict], ctx: ToolContext, tape: Tape, fallback: dict
) -> tuple[str, bool]:
    if not model_available():
        return await _scripted_agent_reply(ctx, tape, fallback)
    return await agent_reply(messages, ctx, tape)


async def _scripted_agent_reply(
    ctx: ToolContext, tape: Tape, fallback: dict
) -> tuple[str, bool]:
    """Used only when no Azure deployment is configured.

    The tools and the guardrail are still real - only the wording is canned.
    """
    for spec in fallback.get("tools", []):
        await run_tool(spec["name"], spec.get("args", {}), ctx, tape)
        if ctx.escalation_reason:
            return "", True
    return fallback.get("agent", ""), False


async def _hold_for_handoff() -> None:
    """Stay on the line while the handoff message is spoken, then hang up.

    The real runner cannot hang up until the TTS has finished the line, and the
    line is roughly twice the length of a normal turn. Without this the mock
    call disappears from the broker dashboard in the same tick it escalates,
    and nobody ever sees the red banner the escalation is supposed to raise.
    """
    await asyncio.sleep(TURN_DELAY_S * 2)


# ------------------------------------------------------------------ the runner

async def run_mock_call(call_id: str) -> None:
    call = await db.calls.find_one({"call_id": call_id})
    lead = await db.leads.find_one({"lead_id": call["lead_id"]})
    script = pick_script(lead["lead_id"])
    tape = Tape(call_id)

    system_prompt = await build_system_prompt(lead)
    ctx = ToolContext(
        call_id=call_id, lead=dict(lead), properties=await match_properties(lead)
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "[the line has connected - greet the caller]"},
    ]

    if not model_available():
        log.warning(
            "no Azure AI Foundry deployment configured - mock call %s will use the "
            "script's canned agent lines. Tools, guardrail and escalation are still live.",
            call_id,
        )

    escalated = False
    try:
        opening, escalated = await _agent_reply(
            messages, ctx, tape, {"agent": script["opening"]}
        )
        if opening:
            await tape.say("agent", opening)
            messages.append({"role": "assistant", "content": opening})

        for step in script["turns"]:
            await asyncio.sleep(TURN_DELAY_S)
            tape.advance(random.randint(300, 900))       # caller picks up the thread
            await tape.say("lead", step["lead"])
            messages.append({"role": "user", "content": step["lead"]})

            # The detector runs before the model is asked for anything.
            reason = escalation.detect(step["lead"])
            if reason:
                tape.advance(random.randint(400, 900))       # barge-in latency
                await escalation.perform_handoff(
                    call_id, lead["lead_id"], reason, tape.elapsed_ms, tape.idx
                )
                tape.idx += 1
                escalated = True
                await _hold_for_handoff()
                break

            tape.advance(random.randint(700, 1500))      # agent response latency
            text, escalated = await _agent_reply(messages, ctx, tape, step)

            if escalated or ctx.escalation_reason:
                await escalation.perform_handoff(
                    call_id, lead["lead_id"], ctx.escalation_reason or "OUT_OF_SCOPE",
                    tape.elapsed_ms, tape.idx,
                )
                tape.idx += 1
                escalated = True
                await _hold_for_handoff()
                break

            if text:
                await tape.say("agent", text)
                messages.append({"role": "assistant", "content": text})
            if ctx.should_end:
                break
    except Exception:
        log.exception("mock call %s failed", call_id)
        await db.calls.update_one(
            {"call_id": call_id},
            {"$set": {"status": "failed", "ended_at": utcnow(),
                      "duration_s": tape.elapsed_ms // 1000}},
        )
        await db.leads.update_one(
            {"lead_id": lead["lead_id"]}, {"$set": {"lead_status": "Queued"}}
        )
        return

    await finalize_call(
        call_id, duration_s=max(1, tape.elapsed_ms // 1000),
        escalated=escalated, memory_candidates=ctx.memory_candidates,
    )
