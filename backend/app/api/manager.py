"""Manager dashboard routes.

The two tracks are reported side by side and never blended. There is no
combined score in this module, and adding one would defeat the point of
grading conversion and safety separately.
"""
import logging
import re
from datetime import timedelta

from fastapi import APIRouter, HTTPException

from app.db import db, next_id, utcnow
from app.models import AnalysisRow, ManagerStats, NewLeadRequest, NewLeadResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.get("/stats", response_model=ManagerStats)
async def stats() -> ManagerStats:
    since = utcnow() - timedelta(hours=24)
    calls = await db.calls.find({"started_at": {"$gte": since}}).to_list(500)

    total = len(calls)
    escalated = sum(1 for c in calls if c.get("escalated"))
    analysed = [c for c in calls if (c.get("analysis") or {}).get("status") == "done"]
    fails = sum(
        1 for c in analysed if (c["analysis"].get("safety") or {}).get("verdict") == "fail"
    )
    completeness = [
        (c["analysis"].get("conversion") or {}).get("completeness", 0.0) for c in analysed
    ]
    ratios = [
        c.get("metrics", {}).get("agent_talk_ratio", 0.0)
        for c in calls
        if c.get("metrics", {}).get("turn_count")
    ]

    return ManagerStats(
        calls_today=total,
        escalation_rate=round(escalated / total, 3) if total else 0.0,
        safety_fails=fails,
        avg_completeness=round(sum(completeness) / len(completeness), 3) if completeness else 0.0,
        avg_talk_ratio=round(sum(ratios) / len(ratios), 3) if ratios else 0.0,
    )


@router.get("/analysis", response_model=list[AnalysisRow])
async def analysis() -> list[AnalysisRow]:
    calls = (
        await db.calls.find({"analysis.status": "done"})
        .sort("started_at", -1)
        .to_list(100)
    )
    if not calls:
        return []

    leads = {
        d["lead_id"]: d
        for d in await db.leads.find(
            {"lead_id": {"$in": list({c["lead_id"] for c in calls})}},
            {"_id": 0, "lead_id": 1, "first_name": 1, "last_name": 1},
        ).to_list(100)
    }

    rows: list[AnalysisRow] = []
    for c in calls:
        conversion = c["analysis"].get("conversion") or {}
        safety = c["analysis"].get("safety") or {}
        lead = leads.get(c["lead_id"], {})
        name = (
            f"{lead.get('first_name', '')[:1]}. {lead.get('last_name', '')}".strip()
            if lead
            else c["lead_id"]
        )
        rows.append(
            AnalysisRow(
                call_id=c["call_id"],
                lead_name=name,
                ended_at=c.get("ended_at"),
                duration_s=c.get("duration_s") or 0,
                conversion_score=conversion.get("track_score", 0.0),
                completeness=conversion.get("completeness", 0.0),
                next_step_secured=conversion.get("next_step_secured", False),
                lead_temperature=conversion.get("lead_temperature", "cold"),
                safety_verdict=safety.get("verdict", "pass"),
                violation_count=len(safety.get("violations", [])),
                escalated=c.get("escalated", False),
            )
        )
    return rows


# E.164: a leading + and 8-15 digits. This route does not dial - telephony/
# dograh/client.py hands it to the orchestrator - but it matters twice over:
# lead's identity on every dashboard and every follow-up, *and* it is what a
# carrier will actually ring. A number in the wrong shape is rejected at the
# door rather than becoming a call that fails at 2am.
PHONE = re.compile(r"^\+[1-9]\d{7,14}$")


@router.post("/leads", response_model=NewLeadResponse, status_code=201)
async def create_lead(body: NewLeadRequest) -> NewLeadResponse:
    """Add a lead by hand. It lands in the queue, ready to call."""
    phone = body.phone.replace(" ", "").replace("-", "")
    if not PHONE.match(phone):
        raise HTTPException(
            422, "Phone must be in international format, e.g. +919812345678"
        )
    if await db.leads.find_one({"phone": phone}):
        raise HTTPException(409, f"A lead with phone {phone} already exists")

    if body.lead_type == "lender" and not (body.subject_property_address or "").strip():
        raise HTTPException(
            422, "A property owner needs the address of the property they listed"
        )

    lo, hi = body.monthly_rent_min, body.monthly_rent_max
    if lo is not None and hi is not None and lo > hi:
        raise HTTPException(422, "Minimum rent cannot exceed maximum rent")

    renter = body.lead_type == "renter"
    lead_id = await next_id("LD", db.leads, "lead_id")
    doc = {
        "lead_id": lead_id,
        "created_at": utcnow(),
        "first_name": body.first_name.strip(),
        "last_name": body.last_name.strip(),
        "email": body.email.strip(),
        "phone": phone,
        "lead_type": body.lead_type,
        "lead_status": "Queued",
        "monthly_rent_min": lo if renter else None,
        "monthly_rent_max": hi if renter else None,
        "property_type": "Apartment" if renter else None,
        "bhk_config": (body.bhk_config or None) if renter else None,
        "furnishing": body.furnishing if renter else None,
        "preferred_areas": [a.strip() for a in body.preferred_areas if a.strip()] if renter else [],
        "subject_property_address": (
            body.subject_property_address.strip() if not renter and body.subject_property_address else None
        ),
        "first_contact_date": None,
        "last_contact_date": None,
        "liked_property_ids": [],
        "shown_property_ids": [],
        "showings_count": 0,
        "appointment_datetime": None,
    }
    await db.leads.insert_one(doc)
    log.info("created %s (%s) from the manager dashboard", lead_id, body.lead_type)
    return NewLeadResponse(lead_id=lead_id, lead_status="Queued")
