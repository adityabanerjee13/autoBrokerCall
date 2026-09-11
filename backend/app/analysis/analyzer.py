"""LLM-2a (conversion) and LLM-2b (safety).

Two independent completions on the `analyzer` deployment. 2b is given the
transcript and the policy but NOT 2a's output - the two tracks must not be able
to contaminate each other, because the whole point of grading on two axes is
that a commercially good call can still be a compliance failure.

Nothing in this module produces a combined score.
"""
import json
import logging
from functools import lru_cache
from pathlib import Path

from app.analysis.schemas import CONVERSION_SCHEMA, SAFETY_SCHEMA
from app.config import policy, settings
from app.db import db
from app.llm import azure_client

log = logging.getLogger(__name__)

RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"


@lru_cache
def rubric(name: str) -> str:
    return (RUBRIC_DIR / f"{name}.md").read_text(encoding="utf-8")


def render_transcript(call: dict) -> str:
    return "\n".join(
        f"[{t['idx']}] {t['role'].upper()}: {t['text']}"
        for t in sorted(call.get("transcript", []), key=lambda x: x["idx"])
    )


def render_tool_calls(call: dict) -> str:
    rows = call.get("tool_calls", [])
    if not rows:
        return "(no tool calls)"
    return "\n".join(
        f"- {r['name']}({json.dumps(r.get('args', {}), default=str)}) -> "
        + ("allowed" if r["allowed"] else f"DENIED {r['reason']}")
        for r in rows
    )


async def _verified_facts_block(call: dict) -> str:
    """What the agent was allowed to say about each property it touched.

    Two separate things, and the judge must not confuse them: the LISTING
    ATTRIBUTES are authoritative structured fields the agent is expected to
    quote, and VERIFIED FACTS are the only prose claims it may make. Passing
    the facts alone makes the judge flag the rent as an unverified claim on
    every well-behaved call.
    """
    pids = {
        r["args"]["property_id"]
        for r in call.get("tool_calls", [])
        if r.get("args", {}).get("property_id")
    }
    if not pids:
        return "(no property was presented)"
    props = await db.properties.find({"property_id": {"$in": list(pids)}}).to_list(20)
    out = []
    for p in props:
        out.append(
            f"{p['property_id']} LISTING ATTRIBUTES (authoritative - quoting these "
            f"is correct, not a violation): address {p['address']}; "
            f"{p['bhk_config']} {p['property_type']}; {p['furnishing']} furnished; "
            f"rent Rs {p['monthly_rent']:,} per month; "
            f"deposit {p['deposit_months']} months; status {p['status']}"
        )
        facts = p.get("verified_facts") or ["none on file"]
        out.append(
            f"{p['property_id']} VERIFIED FACTS (the only prose claims permitted): "
            + "; ".join(facts)
        )
    return "\n".join(out)


# ------------------------------------------------------------------- LLM-2a

async def grade_conversion(call: dict, lead: dict) -> dict:
    required = policy()["required_fields"][lead["lead_type"]]
    if not azure_client.available():
        return _offline_conversion(call, lead, required)

    user = (
        f"LEAD TYPE: {lead['lead_type']}\n"
        f"REQUIRED FIELDS: {', '.join(required)}\n"
        f"FIELDS ALREADY ON FILE BEFORE THE CALL: "
        f"{', '.join(f for f in required if lead.get(f) not in (None, '', [], 0)) or 'none'}\n\n"
        f"TRANSCRIPT\n{render_transcript(call)}\n\n"
        f"TOOL CALLS\n{render_tool_calls(call)}"
    )
    raw = await azure_client.complete_json(
        "analyzer",
        [
            {"role": "system", "content": rubric("conversion")},
            {"role": "user", "content": user},
        ],
        "conversion_track",
        CONVERSION_SCHEMA,
        temperature=0,
    )
    return json.loads(raw)


# ------------------------------------------------------------------- LLM-2b

async def grade_safety(call: dict, lead: dict) -> dict:
    """Deliberately does not receive the conversion track's output."""
    if not azure_client.available():
        return _offline_safety(call)

    pol = policy()
    user = (
        "OPERATING POLICY THE AGENT WAS GIVEN\n"
        f"handoff_message (must be spoken verbatim on escalation):\n"
        f"{' '.join(pol['handoff_message'].split())}\n\n"
        f"{pol['escalation_prompt']}\n\n"
        f"VERIFIED FACTS AVAILABLE TO THE AGENT\n{await _verified_facts_block(call)}\n\n"
        f"THE AGENT RECORDED escalated={call.get('escalated')} "
        f"reason={call.get('escalation_reason')}\n\n"
        f"TRANSCRIPT\n{render_transcript(call)}"
    )
    raw = await azure_client.complete_json(
        "analyzer",
        [
            {"role": "system", "content": rubric("safety")},
            {"role": "user", "content": user},
        ],
        "safety_track",
        SAFETY_SCHEMA,
        temperature=0,
    )
    return json.loads(raw)


# ------------------------------------------------- offline (no deployment set)

def _offline_conversion(call: dict, lead: dict, required: list[str]) -> dict:
    """Deterministic stand-in so the demo runs without an Azure deployment."""
    captured = [f for f in required if lead.get(f) not in (None, "", [], 0)]
    missing = [f for f in required if f not in captured]
    booked = any(
        r["name"] == "book_appointment" and r["allowed"] for r in call.get("tool_calls", [])
    )
    completeness = round(len(captured) / len(required), 2) if required else 0.0

    if call.get("escalated"):
        proposed, temp = None, "cold"
    elif booked:
        proposed, temp = "Appointment Set", "hot"
    elif not missing:
        proposed, temp = "Qualified", "warm"
    else:
        proposed, temp = "Contacted", "warm"

    return {
        "fields_captured": captured,
        "fields_missing": missing,
        "completeness": completeness,
        "next_step_secured": booked,
        "next_step": "viewing booked" if booked else None,
        "objection_handling": {
            "score": 3,
            "rationale": "Graded offline without a model; no objection analysis performed.",
            "turns": [],
        },
        "lead_temperature": temp,
        "proposed_status": proposed,
        "track_score": round(0.4 * completeness + 0.35 * booked + 0.25 * 0.6, 2),
    }


def _offline_safety(call: dict) -> dict:
    denials = [r for r in call.get("tool_calls", []) if not r["allowed"]]
    violations = [
        {
            "rule": "guardrail_denial",
            "turn": -1,
            "quote": r["name"],
            "explanation": f"The guardrail denied {r['name']}: {r['reason']}.",
        }
        for r in denials
        if r["reason"] in ("needs_verification", "not_available")
    ]
    escalated = bool(call.get("escalated"))
    return {
        "verdict": "fail" if violations else "pass",
        "violations": violations,
        "escalation": {
            "should_have": escalated,
            "did": escalated,
            "reason": call.get("escalation_reason"),
            "miss_type": None,
        },
        "unverified_claims": [],
        "pressure_flags": [],
    }


# --------------------------------------------------------------------- runner

async def analyze(call: dict, lead: dict) -> dict:
    """Both tracks. Returns the `calls.analysis` sub-document."""
    conversion = await grade_conversion(call, lead)
    safety = await grade_safety(call, lead)
    return {
        "deployment": settings.azure_deployment_analyzer,
        "conversion": conversion,
        "safety": safety,
    }
