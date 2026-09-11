"""Home-owner dashboard routes.

Everything here is scoped to one owner's own properties, and the payload is
built field by field rather than by projecting a lead document. A renter's
name, contact details, budget, transcript or reason for passing must never
leave this module - the owner sees aggregate interest and a first name for a
confirmed viewing, and nothing else.
"""
import logging

from fastapi import APIRouter, HTTPException

from app.db import db, utcnow
from app.models import (
    ClientDashboard,
    ClientInterest,
    ClientProperty,
    ClientUpcoming,
    LenderOption,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/client", tags=["client"])


@router.get("/lenders", response_model=list[LenderOption])
async def lenders() -> list[LenderOption]:
    """POC selector - there is no auth, so the page picks whose view to show."""
    docs = (
        await db.leads.find(
            {"lead_type": "lender"}, {"_id": 0, "lead_id": 1, "first_name": 1, "last_name": 1}
        )
        .sort("lead_id", 1)
        .to_list(50)
    )
    return [
        LenderOption(lead_id=d["lead_id"], name=f"{d['first_name']} {d['last_name']}")
        for d in docs
    ]


@router.get("/{lead_id}/dashboard", response_model=ClientDashboard)
async def dashboard(lead_id: str) -> ClientDashboard:
    owner = await db.leads.find_one({"lead_id": lead_id, "lead_type": "lender"})
    if owner is None:
        raise HTTPException(404, f"No owner {lead_id}")

    props = (
        await db.properties.find({"owner_lead_id": lead_id}).sort("property_id", 1).to_list(50)
    )
    pids = [p["property_id"] for p in props]

    properties = [
        ClientProperty(
            property_id=p["property_id"],
            address=p["address"],
            bhk_config=p["bhk_config"],
            monthly_rent=p["monthly_rent"],
            status=p["status"],
            furnishing=p["furnishing"],
        )
        for p in props
    ]

    # Aggregate interest only. We read renter documents to count, and we return
    # counts - never the renters behind them.
    shown = {pid: 0 for pid in pids}
    liked = {pid: 0 for pid in pids}
    renters = await db.leads.find(
        {
            "lead_type": "renter",
            "$or": [
                {"shown_property_ids": {"$in": pids}},
                {"liked_property_ids": {"$in": pids}},
            ],
        },
        {"_id": 0, "first_name": 1, "shown_property_ids": 1, "liked_property_ids": 1,
         "appointment_datetime": 1},
    ).to_list(500)

    for r in renters:
        for pid in r.get("shown_property_ids", []):
            if pid in shown:
                shown[pid] += 1
        for pid in r.get("liked_property_ids", []):
            if pid in liked:
                liked[pid] += 1

    interest = [
        ClientInterest(property_id=pid, shown_count=shown[pid], liked_count=liked[pid])
        for pid in pids
    ]

    now = utcnow()
    upcoming: list[ClientUpcoming] = []
    for r in renters:
        appt = r.get("appointment_datetime")
        if not appt or appt <= now:
            continue
        for pid in r.get("liked_property_ids", []):
            if pid in shown:
                upcoming.append(
                    ClientUpcoming(
                        first_name=r["first_name"],  # first name only, by design
                        property_id=pid,
                        appointment_datetime=appt,
                    )
                )
                break
    upcoming.sort(key=lambda u: u.appointment_datetime)

    return ClientDashboard(properties=properties, interest=interest, upcoming=upcoming)
