"""The send button's idempotency and the analysis gate.

These touch Mongo, so they are skipped when nothing is listening on MONGO_URI.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.agent.finalize import apply_gate
from app.config import settings
from app.db import db, utcnow
from app.outbound.send import send

pytestmark = pytest.mark.asyncio


async def mongo_available() -> bool:
    try:
        await asyncio.wait_for(db.messages.database.command("ping"), timeout=8)
        return True
    except Exception:
        return False


@pytest.fixture
async def mongo():
    if not await mongo_available():
        pytest.skip(f"no MongoDB at {settings.mongo_uri}")
    yield


@pytest.fixture
async def draft(mongo):
    lead_id, call_id, message_id = "LD-TEST", "CL-TEST", "MS-TEST"
    await db.leads.delete_many({"lead_id": lead_id})
    await db.messages.delete_many({"message_id": message_id})
    await db.leads.insert_one(
        {
            "lead_id": lead_id, "created_at": utcnow(), "first_name": "Test",
            "last_name": "Lead", "email": "test@example.com", "phone": "+919800000000",
            "lead_type": "renter", "lead_status": "Contacted", "preferred_areas": [],
            "liked_property_ids": [], "shown_property_ids": [], "showings_count": 0,
        }
    )
    await db.messages.insert_one(
        {
            "message_id": message_id, "call_id": call_id, "lead_id": lead_id,
            "whatsapp": {"body": "hello", "status": "pending", "provider_id": None,
                         "sent_at": None, "error": None},
            "email": {"subject": "hello", "body_text": "hello", "status": "pending",
                      "provider_id": None, "sent_at": None, "error": None},
            "status": "draft", "triggered_by": None, "triggered_at": None,
            "created_at": utcnow(),
        }
    )
    yield message_id
    await db.leads.delete_many({"lead_id": lead_id})
    await db.messages.delete_many({"message_id": message_id})


async def test_a_double_click_sends_exactly_once(draft):
    first, second = await asyncio.gather(
        send(draft), send(draft), return_exceptions=True
    )
    results = [first, second]
    ok = [r for r in results if not isinstance(r, Exception)]
    refused = [r for r in results if isinstance(r, HTTPException)]

    assert len(ok) == 1, "exactly one of the two clicks should have sent"
    assert len(refused) == 1 and refused[0].status_code == 409

    doc = await db.messages.find_one({"message_id": draft})
    assert doc["status"] == "sent"
    assert doc["triggered_by"] == "broker-demo"
    assert doc["whatsapp"]["provider_id"] and doc["email"]["provider_id"]


async def test_sending_an_already_sent_message_is_refused(draft):
    await send(draft)
    with pytest.raises(HTTPException) as exc:
        await send(draft)
    assert exc.value.status_code == 409


async def test_safety_failure_overrides_the_conversion_proposal(mongo):
    lead_id = "LD-GATE"
    await db.leads.delete_many({"lead_id": lead_id})
    await db.leads.insert_one(
        {
            "lead_id": lead_id, "created_at": utcnow(), "first_name": "Gate",
            "last_name": "Test", "email": "g@example.com", "phone": "+919800000001",
            "lead_type": "renter", "lead_status": "Calling", "preferred_areas": [],
            "liked_property_ids": [], "shown_property_ids": [], "showings_count": 0,
            "first_contact_date": None,
        }
    )
    lead = await db.leads.find_one({"lead_id": lead_id})

    try:
        await apply_gate(
            lead,
            {
                "conversion": {
                    "proposed_status": "Appointment Set",
                    "fields_captured": [],
                    "track_score": 0.95,
                },
                "safety": {"verdict": "fail"},
            },
        )
        after = await db.leads.find_one({"lead_id": lead_id})
        assert after["lead_status"] == "Escalated", (
            "a safety failure must override the conversion track's proposal, "
            "however well the call converted"
        )
        assert after["last_contact_date"] is not None
    finally:
        await db.leads.delete_many({"lead_id": lead_id})


async def test_a_passing_call_takes_the_conversion_proposal(mongo):
    lead_id = "LD-GATE2"
    await db.leads.delete_many({"lead_id": lead_id})
    await db.leads.insert_one(
        {
            "lead_id": lead_id, "created_at": utcnow(), "first_name": "Gate",
            "last_name": "Two", "email": "g2@example.com", "phone": "+919800000002",
            "lead_type": "renter", "lead_status": "Calling", "preferred_areas": [],
            "liked_property_ids": [], "shown_property_ids": [], "showings_count": 0,
            "first_contact_date": None,
        }
    )
    lead = await db.leads.find_one({"lead_id": lead_id})

    try:
        await apply_gate(
            lead,
            {
                "conversion": {
                    "proposed_status": "Qualified",
                    "fields_captured": [],
                    "track_score": 0.6,
                },
                "safety": {"verdict": "pass"},
            },
        )
        after = await db.leads.find_one({"lead_id": lead_id})
        assert after["lead_status"] == "Qualified"
    finally:
        await db.leads.delete_many({"lead_id": lead_id})
