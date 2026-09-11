"""The guardrail's five rules, one test each.

Every case builds its properties into the ToolContext so `check` never needs a
database - the rules themselves are pure.
"""
import pytest

from app.agent.guardrail import check
from app.agent.tools import ToolContext

QUALIFIED_RENTER = {
    "lead_id": "LD-0001",
    "lead_type": "renter",
    "lead_status": "Queued",
    "monthly_rent_min": 45000,
    "monthly_rent_max": 60000,
    "preferred_areas": ["Sector 82"],
    "bhk_config": "3BHK",
}

AVAILABLE = {
    "property_id": "PR-4425",
    "status": "available",
    "verified_facts": ["Pets allowed with society NOC", "Lock-in 11 months"],
}
LET = {"property_id": "PR-4413", "status": "let", "verified_facts": []}


def ctx(lead: dict, properties: list[dict] | None = None) -> ToolContext:
    return ToolContext(call_id="CL-0001", lead=dict(lead), properties=properties or [])


@pytest.mark.asyncio
async def test_tool_outside_the_registry_for_this_lead_type_is_denied():
    owner = dict(QUALIFIED_RENTER, lead_type="lender", subject_property_address="B-1204")
    allowed, reason = await check("search_properties", {}, ctx(owner), escalated=False)
    assert (allowed, reason) == (False, "unknown_tool")

    allowed, reason = await check("no_such_tool", {}, ctx(QUALIFIED_RENTER), escalated=False)
    assert (allowed, reason) == (False, "unknown_tool")


@pytest.mark.asyncio
async def test_escalated_call_freezes_everything_except_hanging_up():
    c = ctx(QUALIFIED_RENTER, [AVAILABLE])
    for tool in ("capture_field", "present_property", "note_memory"):
        allowed, reason = await check(tool, {"property_id": "PR-4425"}, c, escalated=True)
        assert (allowed, reason) == (False, "agent_frozen"), tool

    allowed, _ = await check("end_call", {"disposition": "escalated"}, c, escalated=True)
    assert allowed is True


@pytest.mark.asyncio
async def test_presenting_before_qualifying_is_denied():
    unqualified = dict(QUALIFIED_RENTER, bhk_config=None, preferred_areas=[])
    c = ctx(unqualified, [AVAILABLE])
    for tool in ("search_properties", "present_property", "book_appointment"):
        allowed, reason = await check(tool, {"property_id": "PR-4425"}, c, escalated=False)
        assert (allowed, reason) == (False, "qualify_first"), tool

    # capture_field is how the agent gets out of this state, so it stays open.
    allowed, _ = await check(
        "capture_field", {"field": "bhk_config", "value": "3BHK"}, c, escalated=False
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_property_that_is_not_available_cannot_be_offered():
    c = ctx(QUALIFIED_RENTER, [LET])
    allowed, reason = await check(
        "present_property", {"property_id": "PR-4413"}, c, escalated=False
    )
    assert (allowed, reason) == (False, "not_available")

    allowed, reason = await check(
        "book_appointment",
        {"property_id": "PR-4413", "when": "2026-09-12T11:00:00+05:30"},
        c,
        escalated=False,
    )
    assert (allowed, reason) == (False, "not_available")


@pytest.mark.asyncio
async def test_argument_asserting_an_unverified_fact_is_denied():
    c = ctx(QUALIFIED_RENTER, [AVAILABLE])

    allowed, reason = await check(
        "present_property",
        {"property_id": "PR-4425", "note": "there is no lock-in period at all"},
        c,
        escalated=False,
    )
    assert (allowed, reason) == (False, "needs_verification")

    # A claim that is in verified_facts is fine.
    allowed, _ = await check(
        "present_property",
        {"property_id": "PR-4425", "note": "pets allowed with society NOC"},
        c,
        escalated=False,
    )
    assert allowed is True


@pytest.mark.asyncio
async def test_a_qualified_lead_and_an_available_property_is_allowed():
    c = ctx(QUALIFIED_RENTER, [AVAILABLE])
    allowed, reason = await check(
        "present_property", {"property_id": "PR-4425"}, c, escalated=False
    )
    assert (allowed, reason) == (True, None)
