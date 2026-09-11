"""Tool schemas and executors for LLM-1.

Deliberately absent, and not to be added: any payment or token tool, any
loan/EMI/tax quote tool, any message-sending tool, and any tool that can move
a property back to `available`.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.db import db, utcnow
from app.models import ESCALATION_REASONS

log = logging.getLogger(__name__)

# Which lead types may see which tool. The guardrail reads this.
TOOL_LEAD_TYPES: dict[str, set[str]] = {
    "capture_field": {"renter", "lender"},
    "search_properties": {"renter"},
    "present_property": {"renter"},
    "book_appointment": {"renter"},
    "note_memory": {"renter", "lender"},
    "escalate_to_human": {"renter", "lender"},
    "end_call": {"renter", "lender"},
}

CAPTURABLE_FIELDS = [
    "monthly_rent_min", "monthly_rent_max", "preferred_areas", "bhk_config",
    "property_type", "furnishing", "subject_property_address",
]

MEMORY_KINDS = [
    "preference", "constraint", "rejection_reason", "relationship",
    "communication_style", "commitment", "sensitivity",
]

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "capture_field",
            "description": "Record one fact the caller stated about their requirement. Call it the moment they say it; never batch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": CAPTURABLE_FIELDS},
                    "value": {
                        "description": "Number for rent fields, array of strings for preferred_areas, string otherwise."
                    },
                },
                "required": ["field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_properties",
            "description": "Find available rentals matching the caller's stated requirement. Requires the qualifying fields first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "areas": {"type": "array", "items": {"type": "string"}},
                    "rent_min": {"type": "integer"},
                    "rent_max": {"type": "integer"},
                    "bhk": {"type": "string"},
                },
                "required": ["areas", "rent_min", "rent_max", "bhk"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "present_property",
            "description": "Mark that you are describing this property to the caller. Only for properties that are available.",
            "parameters": {
                "type": "object",
                "properties": {"property_id": {"type": "string"}},
                "required": ["property_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a viewing slot the caller has verbally agreed to.",
            "parameters": {
                "type": "object",
                "properties": {
                    "property_id": {"type": "string"},
                    "when": {"type": "string", "description": "ISO 8601 datetime"},
                },
                "required": ["property_id", "when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "note_memory",
            "description": "Note something durable about this person that should carry into future calls.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": MEMORY_KINDS},
                    "text": {"type": "string"},
                },
                "required": ["kind", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Hand this call to a human colleague immediately. Say nothing else first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "enum": list(ESCALATION_REASONS)}
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_call",
            "description": "End the call politely.",
            "parameters": {
                "type": "object",
                "properties": {"disposition": {"type": "string"}},
                "required": ["disposition"],
            },
        },
    },
]


@dataclass
class ToolContext:
    """Everything an executor may touch. No executor opens its own connections."""

    call_id: str
    lead: dict
    properties: list[dict] = field(default_factory=list)
    memory_candidates: list[dict] = field(default_factory=list)
    presented: list[str] = field(default_factory=list)
    should_end: bool = False
    escalation_reason: str | None = None

    def property_by_id(self, property_id: str) -> dict | None:
        return next(
            (p for p in self.properties if p["property_id"] == property_id), None
        )


def _coerce_int(value: Any) -> int | None:
    try:
        return int(str(value).replace(",", "").replace("Rs", "").strip())
    except (TypeError, ValueError):
        return None


async def execute(name: str, args: dict, ctx: ToolContext) -> str:
    """Run an allowed tool. Returns the string result handed back to the model."""
    handler = _HANDLERS.get(name)
    if handler is None:  # unreachable - the guardrail denies unknown tools first
        return "error: unknown tool"
    return await handler(args, ctx)


async def _capture_field(args: dict, ctx: ToolContext) -> str:
    fld = args.get("field")
    value = args.get("value")
    if fld not in CAPTURABLE_FIELDS:
        return f"error: {fld} is not a field you can capture"

    if fld in ("monthly_rent_min", "monthly_rent_max"):
        value = _coerce_int(value)
        if value is None:
            return "error: rent must be a number of rupees per month"
    elif fld == "preferred_areas":
        if isinstance(value, str):
            value = [a.strip() for a in value.split(",") if a.strip()]
        value = list(value or [])

    ctx.lead[fld] = value
    await db.leads.update_one(
        {"lead_id": ctx.lead["lead_id"]}, {"$set": {fld: value}}
    )
    return f"captured {fld}"


async def _search_properties(args: dict, ctx: ToolContext) -> str:
    query: dict = {"status": "available"}
    if args.get("bhk"):
        query["bhk_config"] = args["bhk"]
    if args.get("areas"):
        query["locality"] = {"$in": list(args["areas"])}
    rent_min, rent_max = _coerce_int(args.get("rent_min")), _coerce_int(args.get("rent_max"))
    if rent_min or rent_max:
        band: dict = {}
        if rent_min:
            band["$gte"] = int(rent_min * 0.9)
        if rent_max:
            band["$lte"] = int(rent_max * 1.1)
        query["monthly_rent"] = band

    found = await db.properties.find(query).limit(3).to_list(3)
    if not found:
        query.pop("locality", None)
        found = await db.properties.find(query).limit(3).to_list(3)

    known = {p["property_id"] for p in ctx.properties}
    ctx.properties.extend(p for p in found if p["property_id"] not in known)

    if not found:
        return "no matching available properties - say you will come back with options"
    return "; ".join(
        f"{p['property_id']} {p['bhk_config']} {p['locality']} Rs {p['monthly_rent']:,}/mo"
        for p in found
    )


async def _present_property(args: dict, ctx: ToolContext) -> str:
    pid = args.get("property_id", "")
    prop = ctx.property_by_id(pid) or await db.properties.find_one({"property_id": pid})
    if prop is None:
        return "error: no such property"
    if prop["property_id"] not in ctx.presented:
        ctx.presented.append(prop["property_id"])
    # Deliberately does not touch properties.status: a presented property stays
    # `available` so a viewing can still be booked against it, and no tool in
    # this system is allowed to move a property back to `available` either way.
    await db.leads.update_one(
        {"lead_id": ctx.lead["lead_id"]},
        {"$addToSet": {"shown_property_ids": pid}, "$inc": {"showings_count": 1}},
    )
    facts = prop.get("verified_facts") or ["none on file"]
    return (
        f"presenting {pid}: {prop['address']}, {prop['bhk_config']}, "
        f"Rs {prop['monthly_rent']:,}/mo, deposit {prop['deposit_months']} months. "
        f"VERIFIED FACTS: {'; '.join(facts)}"
    )


async def _book_appointment(args: dict, ctx: ToolContext) -> str:
    pid = args.get("property_id", "")
    when_raw = args.get("when", "")
    try:
        when = datetime.fromisoformat(str(when_raw).replace("Z", "+00:00"))
    except ValueError:
        return "error: could not read that date and time - confirm the slot again"

    await db.leads.update_one(
        {"lead_id": ctx.lead["lead_id"]},
        {
            "$set": {"appointment_datetime": when, "lead_status": "Appointment Set"},
            "$addToSet": {"liked_property_ids": pid},
        },
    )
    ctx.lead["appointment_datetime"] = when
    return f"viewing booked for {pid} at {when.isoformat()}"


async def _note_memory(args: dict, ctx: ToolContext) -> str:
    kind = args.get("kind")
    if kind not in MEMORY_KINDS:
        return f"error: {kind} is not a memory kind"
    ctx.memory_candidates.append(
        {
            "kind": kind,
            "text": str(args.get("text", "")).strip(),
            "call_id": ctx.call_id,
            "created_at": utcnow(),
        }
    )
    return "noted"


async def _escalate_to_human(args: dict, ctx: ToolContext) -> str:
    reason = args.get("reason")
    if reason not in ESCALATION_REASONS:
        reason = "OUT_OF_SCOPE"
    ctx.escalation_reason = reason
    return "escalated"


async def _end_call(args: dict, ctx: ToolContext) -> str:
    ctx.should_end = True
    return f"call ended: {args.get('disposition', 'completed')}"


_HANDLERS = {
    "capture_field": _capture_field,
    "search_properties": _search_properties,
    "present_property": _present_property,
    "book_appointment": _book_appointment,
    "note_memory": _note_memory,
    "escalate_to_human": _escalate_to_human,
    "end_call": _end_call,
}
