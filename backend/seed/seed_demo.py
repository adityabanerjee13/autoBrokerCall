"""Populate the five collections with a demo-ready dataset.

Run:  python seed/seed_demo.py
It drops and rewrites all five collections, so it is safe to re-run.
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import db, ensure_indexes  # noqa: E402

NOW = datetime.now(timezone.utc)


def ago(**kw) -> datetime:
    return NOW - timedelta(**kw)


def ahead(**kw) -> datetime:
    return NOW + timedelta(**kw)


# ------------------------------------------------------------------ owners

# Exactly one client - the owner whose portfolio the Client dashboard shows.
# A single Gurugram landlord holding all eight units, so the dashboard's
# selector has one obvious answer and every property on it belongs to them.
LENDERS = [
    {
        "lead_id": "LD-0041", "first_name": "Ramesh", "last_name": "Iyer",
        "email": "ramesh.iyer@example.com", "phone": "+919810011221",
        "subject_property_address": "B-1204, Emerald Court, Sector 93, Gurugram",
        "lead_status": "Contacted", "created_at": ago(days=40),
    },
]

OWNER = LENDERS[0]["lead_id"]

PROPERTIES = [
    # Sector 93
    ("PR-4412", OWNER, "B-1204, Emerald Court, Sector 93, Gurugram", "Sector 93",
     "Apartment", "3BHK", "semi", 52000, 2, "available",
     ["Pets allowed with society NOC", "Lock-in 11 months", "Two covered parking bays"]),
    ("PR-4413", OWNER, "B-0806, Emerald Court, Sector 93, Gurugram", "Sector 93",
     "Apartment", "2BHK", "unfurnished", 38000, 2, "let",
     ["Lock-in 11 months", "Maintenance billed to tenant"]),
    ("PR-4414", OWNER, "C-0301, Emerald Court, Sector 93, Gurugram", "Sector 93",
     "Apartment", "3BHK", "full", 61000, 3, "under_offer",
     ["No pets", "Society power backup 5 KVA", "Lock-in 11 months"]),

    # Sector 53
    ("PR-4418", OWNER, "T3-905, Vipul Belmonte, Sector 53, Gurugram", "Sector 53",
     "Apartment", "3BHK", "full", 58000, 2, "available",
     ["Pets allowed", "Club house included in maintenance", "Lock-in 11 months"]),
    ("PR-4419", OWNER, "T1-410, Vipul Belmonte, Sector 53, Gurugram", "Sector 53",
     "Apartment", "2BHK", "semi", 44000, 2, "shown",
     ["Lock-in 11 months", "One covered parking bay"]),

    # Sector 82
    ("PR-4425", OWNER, "A-702, Palm Grove Heights, Sector 82, Gurugram", "Sector 82",
     "Apartment", "3BHK", "semi", 47000, 2, "available",
     ["Pets allowed with society NOC", "Lock-in 11 months", "Piped gas connection"]),
    ("PR-4426", OWNER, "A-1105, Palm Grove Heights, Sector 82, Gurugram", "Sector 82",
     "Apartment", "2BHK", "semi", 36000, 2, "available",
     ["No pets", "Lock-in 11 months"]),
    ("PR-4427", OWNER, "D-201, Palm Grove Heights, Sector 82, Gurugram", "Sector 82",
     "Apartment", "4BHK", "full", 78000, 3, "paused",
     ["Owner travelling until next month", "Lock-in 11 months"]),
]

def lead_doc(**kw) -> dict:
    base = {
        "created_at": NOW, "first_name": "", "last_name": "", "email": "",
        "phone": "", "lead_type": "renter", "lead_status": "Queued",
        "monthly_rent_min": None, "monthly_rent_max": None, "property_type": None,
        "bhk_config": None, "furnishing": None, "preferred_areas": [],
        "subject_property_address": None, "first_contact_date": None,
        "last_contact_date": None, "liked_property_ids": [], "shown_property_ids": [],
        "showings_count": 0, "appointment_datetime": None,
    }
    base.update(kw)
    return base


def build_leads() -> list[dict]:
    """Only the owner. Renters arrive through the manager's Add lead form."""
    docs: list[dict] = []
    for spec in LENDERS:
        docs.append(lead_doc(
            lead_type="lender", property_type="Apartment",
            first_contact_date=ago(days=12), last_contact_date=ago(days=12), **spec
        ))
    return docs


def build_properties() -> list[dict]:
    return [
        {
            "property_id": pid, "owner_lead_id": owner, "address": addr,
            "locality": locality, "property_type": ptype, "bhk_config": bhk,
            "furnishing": furn, "monthly_rent": rent, "deposit_months": dep,
            "status": status, "verified_facts": facts,
            "created_at": ago(days=30), "updated_at": ago(days=4),
        }
        for (pid, owner, addr, locality, ptype, bhk, furn, rent, dep, status, facts)
        in PROPERTIES
    ]


async def main() -> None:
    await ensure_indexes()

    for coll in (db.leads, db.properties, db.lead_memory, db.calls, db.messages):
        await coll.delete_many({})

    await db.leads.insert_many(build_leads())
    await db.properties.insert_many(build_properties())
    # calls, messages and lead_memory start empty: they are produced by calls,
    # and every seeded example referenced a renter that no longer exists.

    counts = {
        "leads": await db.leads.count_documents({}),
        "properties": await db.properties.count_documents({}),
        "lead_memory": await db.lead_memory.count_documents({}),
        "calls": await db.calls.count_documents({}),
        "messages": await db.messages.count_documents({}),
    }
    for name, n in counts.items():
        print(f"  {name:<12} {n}")
    print("\nseeded. One owner and their Gurugram portfolio. "
          "Add renters from the Manager dashboard.")


if __name__ == "__main__":
    asyncio.run(main())
