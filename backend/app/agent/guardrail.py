"""Allow or deny every proposed tool call, before it executes.

The result is appended to `calls.tool_calls` either way, and a denial reason is
handed back to the model as the tool result so it can recover gracefully.
"""
import logging
import re

from app.config import policy
from app.db import db
from app.agent.tools import TOOL_LEAD_TYPES, ToolContext

log = logging.getLogger(__name__)

# Subjects the agent may only speak to from a property's verified_facts.
_FACT_SUBJECTS = re.compile(
    r"\b(deposit|lock[- ]?in|pet|society|noc|maintenance|parking|"
    r"power ?backup|water|club ?house|notice period)\b",
    re.IGNORECASE,
)

_QUALIFY_GATED = {"search_properties", "present_property", "book_appointment"}
_PROPERTY_GATED = {"present_property", "book_appointment"}

DENIAL_MESSAGE = {
    "unknown_tool": "That tool is not available on this call.",
    "agent_frozen": "This call has been handed to a colleague. Do not say anything further.",
    "qualify_first": "You do not have the required details yet. Ask for them first.",
    "not_available": "That property is not available. Do not offer it.",
    "needs_verification": "That is not in VERIFIED FACTS. Say you will confirm and come back.",
}


def _missing_required(lead: dict) -> list[str]:
    required = policy()["required_fields"][lead["lead_type"]]
    return [f for f in required if lead.get(f) in (None, "", [], 0)]


def _asserts_unverified_fact(args: dict, prop: dict | None) -> str | None:
    """True when a string argument states a fact not present in verified_facts."""
    facts = " ".join(prop.get("verified_facts", [])).lower() if prop else ""
    for key, value in args.items():
        if key in ("property_id", "when") or not isinstance(value, str):
            continue
        if not _FACT_SUBJECTS.search(value):
            continue
        claim_words = {w for w in re.findall(r"[a-z]{4,}", value.lower())}
        if not claim_words or not claim_words.issubset(set(re.findall(r"[a-z]{4,}", facts))):
            return value
    return None


async def check(name: str, args: dict, ctx: ToolContext, escalated: bool) -> tuple[bool, str | None]:
    """Returns (allowed, reason). Reason is None when allowed."""
    # 1. tool not in the registry for this lead_type
    allowed_types = TOOL_LEAD_TYPES.get(name)
    if allowed_types is None or ctx.lead["lead_type"] not in allowed_types:
        return False, "unknown_tool"

    # 2. call already escalated - the agent is frozen apart from hanging up
    if escalated and name != "end_call":
        return False, "agent_frozen"

    # 3. qualifying fields missing
    if name in _QUALIFY_GATED and _missing_required(ctx.lead):
        return False, "qualify_first"

    prop = None
    if name in _PROPERTY_GATED:
        pid = args.get("property_id")
        prop = ctx.property_by_id(pid) if pid else None
        if prop is None and pid:
            prop = await db.properties.find_one({"property_id": pid})
        # 4. property is not available
        if prop is None or prop.get("status") != "available":
            return False, "not_available"

    # 5. an argument asserts a fact that is not verified
    if _asserts_unverified_fact(args, prop):
        return False, "needs_verification"

    return True, None
