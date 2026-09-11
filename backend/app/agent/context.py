"""System prompt assembly for LLM-1.

Seven segments, concatenated in a fixed order. Deterministic - there is no
retrieval, no vector search and no mid-call lookup anywhere in this module.
"""
import logging

from app.config import policy
from app.db import db
from app.memory.reader import read_memory_block

log = logging.getLogger(__name__)

ROLE_SEGMENT = """You are Asha, a voice assistant calling on behalf of a residential
rental brokerage in Gurugram, India. You are on a live phone call. The person you
are speaking to is on the other end of the line right now.

HARD CONSTRAINTS.
- Speak in short spoken sentences. One question at a time. Never read out lists.
- All money is MONTHLY RENT in Indian rupees. Never present a figure as a sale price.
- You may not take payments, quote loans, EMI, interest, stamp duty or tax, give
  legal advice, or send any message. You have no tools for these and must not
  improvise them.
- Never invent a fact about a property or a society. Use VERIFIED FACTS only.
- Record every fact the caller gives you with capture_field as they say it.
- End the call with end_call when the objective is met or the caller wants to stop."""

OBJECTIVE_BY_STATUS = {
    "New": "First contact. Introduce yourself, confirm you are speaking to the right person, and qualify from scratch.",
    "Queued": "First contact. Introduce yourself, confirm you are speaking to the right person, and qualify from scratch.",
    "Calling": "First contact. Introduce yourself, confirm you are speaking to the right person, and qualify from scratch.",
    "Contacted": "Follow-up. Fill the gaps listed under MISSING, then present a property and offer a viewing.",
    "Qualified": "This lead is qualified. Present a matching property and secure a viewing slot.",
    "Appointment Set": "A viewing is already booked. Confirm the slot still works and answer any questions from VERIFIED FACTS only.",
    "Escalated": "This lead was escalated previously. Keep it brief, confirm nothing, and end the call.",
    "Closed": "Courtesy follow-up only. Do not re-qualify.",
    "Unqualified": "Courtesy follow-up only. Do not re-qualify.",
}

_RENTER_DIGEST_FIELDS = [
    "monthly_rent_min", "monthly_rent_max", "preferred_areas",
    "bhk_config", "property_type", "furnishing",
]
_LENDER_DIGEST_FIELDS = ["subject_property_address"]


def _fmt(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def lead_digest(lead: dict) -> str:
    fields = _RENTER_DIGEST_FIELDS if lead["lead_type"] == "renter" else _LENDER_DIGEST_FIELDS
    known, missing = [], []
    for f in fields:
        v = lead.get(f)
        if v in (None, "", [], 0):
            missing.append(f)
        else:
            known.append(f"{f}: {_fmt(v)}")

    lines = [
        "LEAD",
        f"name: {lead['first_name']} {lead['last_name']}",
        f"type: {lead['lead_type']}",
        f"status: {lead['lead_status']}",
    ]
    lines.append("KNOWN")
    lines += [f"- {k}" for k in known] or ["- nothing on file"]
    lines.append("MISSING (ask for these)")
    lines += [f"- {m}" for m in missing] or ["- nothing"]
    return "\n".join(lines)


def format_properties(props: list[dict]) -> str:
    if not props:
        return "PROPERTIES\nNo matching available properties. Do not invent one."
    out = ["PROPERTIES (available, quote monthly rent only)"]
    for p in props:
        out.append(
            f"- {p['property_id']} | {p['address']} | {p['bhk_config']} "
            f"{p['property_type']} | {p['furnishing']} | Rs {p['monthly_rent']:,}/mo "
            f"| deposit {p['deposit_months']} months"
        )
        for fact in p.get("verified_facts", []):
            out.append(f"    VERIFIED FACT: {fact}")
    return "\n".join(out)


async def match_properties(lead: dict, limit: int = 5) -> list[dict]:
    """Deterministic filter over available properties. Not a search index."""
    query: dict = {"status": "available"}
    if lead["lead_type"] == "renter":
        rent_max = lead.get("monthly_rent_max")
        rent_min = lead.get("monthly_rent_min")
        if rent_max or rent_min:
            band: dict = {}
            if rent_max:
                band["$lte"] = int(rent_max * 1.1)
            if rent_min:
                band["$gte"] = int(rent_min * 0.9)
            query["monthly_rent"] = band
        if lead.get("bhk_config"):
            query["bhk_config"] = lead["bhk_config"]
        if lead.get("preferred_areas"):
            query["locality"] = {"$in": lead["preferred_areas"]}
    else:
        query["owner_lead_id"] = lead["lead_id"]

    props = await db.properties.find(query).limit(limit).to_list(limit)
    if not props and lead["lead_type"] == "renter":
        # Widen once rather than return nothing: drop locality, keep the budget.
        query.pop("locality", None)
        props = await db.properties.find(query).limit(limit).to_list(limit)
    return props


async def build_system_prompt(lead: dict) -> str:
    """Segments 1-7 in order. Segment 5 is omitted entirely when absent."""
    pol = policy()
    segments: list[str] = [ROLE_SEGMENT]

    # 2. policy for lead_type
    segments.append(
        pol["renter_policy"] if lead["lead_type"] == "renter" else pol["lender_policy"]
    )

    # 3. escalation instructions, verbatim
    segments.append(pol["escalation_prompt"])

    # 4. lead digest
    segments.append(lead_digest(lead))

    # 5. memory block, verbatim - omitted entirely when there is none
    block = await read_memory_block(lead["lead_id"])
    if block:
        segments.append(block)

    # 6. matching properties with verified facts
    props = await match_properties(lead)
    segments.append(format_properties(props))

    # 7. objective for this call
    objective = OBJECTIVE_BY_STATUS.get(lead["lead_status"], OBJECTIVE_BY_STATUS["New"])
    required = pol["required_fields"][lead["lead_type"]]
    segments.append(
        "OBJECTIVE\n"
        f"{objective}\n"
        f"You must have all of these before presenting or booking: {', '.join(required)}."
    )

    return "\n\n".join(s.strip() for s in segments)
