"""Broker dashboard routes: the queue, the live call, and completed calls."""
import logging

from fastapi import APIRouter

from app.db import db, utcnow
from app.models import ActiveCall, CompletedCall, LeadRow, MessagePreview, ToolChip

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/broker", tags=["broker"])

QUEUE_STATUSES = ["Queued", "New", "Contacted", "Qualified"]

# The queue is prospective tenants waiting to be called. Property owners are
# clients, not call targets: they are served by the Client dashboard, and
# putting them here invites someone to cold-call their own customer.
QUEUE_LEAD_TYPES = ["renter"]
LEAD_ROW_FIELDS = {
    "_id": 0, "lead_id": 1, "first_name": 1, "last_name": 1, "lead_type": 1,
    "lead_status": 1, "phone": 1, "monthly_rent_min": 1, "monthly_rent_max": 1,
    "bhk_config": 1, "preferred_areas": 1, "subject_property_address": 1,
    "created_at": 1, "last_contact_date": 1,
}


def _lead_row(doc: dict) -> LeadRow:
    return LeadRow(**{k: v for k, v in doc.items() if k in LEAD_ROW_FIELDS})


@router.get("/queue", response_model=list[LeadRow])
async def queue() -> list[LeadRow]:
    docs = (
        await db.leads.find(
            {
                "lead_status": {"$in": QUEUE_STATUSES},
                "lead_type": {"$in": QUEUE_LEAD_TYPES},
            },
            LEAD_ROW_FIELDS,
        )
        .sort("created_at", 1)
        .to_list(100)
    )
    return [_lead_row(d) for d in docs]


@router.get("/active", response_model=ActiveCall | None)
async def active() -> ActiveCall | None:
    call = await db.calls.find_one({"status": "in_progress"}, sort=[("started_at", -1)])
    if call is None:
        return None
    lead = await db.leads.find_one({"lead_id": call["lead_id"]}, LEAD_ROW_FIELDS)
    if lead is None:
        return None

    started = call["started_at"]
    return ActiveCall(
        call_id=call["call_id"],
        lead=_lead_row(lead),
        started_at=started,
        elapsed_s=max(0, int((utcnow() - started).total_seconds())),
        transcript=sorted(call.get("transcript", []), key=lambda t: t["idx"]),
        tool_calls=[
            ToolChip(name=t["name"], allowed=t["allowed"], reason=t.get("reason"))
            for t in call.get("tool_calls", [])
        ],
        escalated=call.get("escalated", False),
        escalation_reason=call.get("escalation_reason"),
    )


@router.get("/completed", response_model=list[CompletedCall])
async def completed() -> list[CompletedCall]:
    calls = (
        await db.calls.find({"status": {"$in": ["completed", "failed"]}})
        .sort("started_at", -1)
        .to_list(50)
    )
    if not calls:
        return []

    lead_ids = list({c["lead_id"] for c in calls})
    call_ids = [c["call_id"] for c in calls]
    leads = {
        d["lead_id"]: d
        for d in await db.leads.find({"lead_id": {"$in": lead_ids}}, LEAD_ROW_FIELDS).to_list(50)
    }
    messages = {
        m["call_id"]: m
        for m in await db.messages.find({"call_id": {"$in": call_ids}}).to_list(50)
    }

    rows: list[CompletedCall] = []
    for c in calls:
        lead = leads.get(c["lead_id"])
        if lead is None:
            continue
        msg = messages.get(c["call_id"])
        preview = None
        if msg is not None:
            body = msg["whatsapp"]["body"]
            preview = MessagePreview(
                message_id=msg["message_id"],
                status=msg["status"],
                whatsapp_preview=body,
                email_subject=msg["email"]["subject"],
            )
        rows.append(
            CompletedCall(
                call_id=c["call_id"],
                lead=_lead_row(lead),
                ended_at=c.get("ended_at"),
                duration_s=c.get("duration_s") or 0,
                escalated=c.get("escalated", False),
                escalation_reason=c.get("escalation_reason"),
                analysis_status=(c.get("analysis") or {}).get("status", "pending"),
                message=preview,
            )
        )
    return rows
