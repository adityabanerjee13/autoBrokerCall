"""LLM-3: draft the follow-up.

Writes one `messages` document per call at status "draft", with both channel
bodies filled in. It has no send capability and never will - drafting and
sending are separated so that a model can never put a message in front of a
customer without a person clicking the button in send.py.
"""
import json
import logging
from zoneinfo import ZoneInfo

from app.analysis.schemas import MESSAGE_SCHEMA
from app.db import db, next_id, utcnow
from app.llm import azure_client

log = logging.getLogger(__name__)

# Every lead and every property in this product is in Gurugram. Times are
# stored in UTC and must be written back to the customer in local time.
IST = ZoneInfo("Asia/Kolkata")


def _local_slot(when) -> str:
    """"Saturday 12 September at 11:00 am", in Gurugram time.

    Built by hand rather than with %-I, which is a glibc extension and raises
    on Windows.
    """
    local = when.astimezone(IST)
    hour = local.hour % 12 or 12
    meridiem = "am" if local.hour < 12 else "pm"
    return f"{local:%A %d %B} at {hour}:{local:%M} {meridiem}"

SYSTEM = """You write the follow-up a rental broker sends after a call, in two forms:
a WhatsApp message and an email.

Voice: a professional Indian broker writing to a customer they just spoke to.
Warm, brief, specific. No emoji, no exclamation marks, no marketing language.

Rules.
- Reference only what was actually said on the call and the properties actually
  presented. Never introduce a property, a price, a date or a term that is not
  in the material you are given.
- Money is monthly rent in rupees. Write it as Rs 52,000 per month.
- State a fact about a property only if it appears in VERIFIED FACTS. Otherwise
  write that you will confirm it.
- If a next step was agreed, restate it with its time. If not, offer to send
  options and stop there. Never invent a viewing.
- If the call was handed to a colleague, do not explain why. Write a short note
  saying a colleague will call back shortly, and nothing about the subject.
- WhatsApp: under 60 words, no subject line, no signature block.
- Email: a concrete subject line and a body under 150 words, signed "Asha,
  on behalf of the team"."""


def _offline_draft(lead: dict, call: dict, presented: list[dict]) -> dict:
    """Deterministic stand-in so the demo runs without an Azure deployment."""
    name = lead["first_name"]
    if call.get("escalated"):
        wa = (
            f"Hello {name}, thank you for your time on the call just now. "
            "One of my colleagues will call you back on this number shortly to "
            "take this forward."
        )
        return {
            "whatsapp_body": wa,
            "email_subject": "Following up on our call",
            "email_body_text": f"Hello {name},\n\n{wa}\n\nAsha, on behalf of the team",
        }

    if presented:
        p = presented[0]
        detail = (
            f"{p['bhk_config']} at {p['address']}, Rs {p['monthly_rent']:,} per month, "
            f"{p['furnishing']} furnished"
        )
    else:
        detail = "a shortlist matching what you described"

    appt = lead.get("appointment_datetime")
    tail = (
        f" We are confirmed for the viewing on {_local_slot(appt)}."
        if appt
        else " I will send you a couple of options that fit and we can plan a viewing."
    )
    wa = f"Hello {name}, thank you for your time. Sharing details of {detail}.{tail}"
    return {
        "whatsapp_body": wa,
        "email_subject": f"Rental options for you in {', '.join(lead.get('preferred_areas') or ['Gurugram'])}",
        "email_body_text": (
            f"Hello {name},\n\nThank you for speaking with me today. "
            f"As discussed, I am sharing details of {detail}.{tail}\n\n"
            "Do let me know if you would like anything else shortlisted.\n\n"
            "Asha, on behalf of the team"
        ),
    }


async def draft_followup(call_id: str) -> str | None:
    """Insert the draft. Returns the message_id, or None when one already exists."""
    existing = await db.messages.find_one({"call_id": call_id})
    if existing:
        log.info("follow-up already drafted for %s", call_id)
        return existing["message_id"]

    call = await db.calls.find_one({"call_id": call_id})
    lead = await db.leads.find_one({"lead_id": call["lead_id"]})

    pids = [
        r["args"]["property_id"]
        for r in call.get("tool_calls", [])
        if r["name"] == "present_property" and r["allowed"] and r.get("args", {}).get("property_id")
    ]
    presented = (
        await db.properties.find({"property_id": {"$in": pids}}).to_list(5) if pids else []
    )

    if azure_client.available():
        facts = "\n".join(
            f"{p['property_id']} ({p['address']}, {p['bhk_config']}, "
            f"Rs {p['monthly_rent']:,}/mo, {p['furnishing']}): "
            + "; ".join(p.get("verified_facts") or ["none on file"])
            for p in presented
        ) or "(no property was presented on this call)"
        transcript = "\n".join(
            f"{t['role'].upper()}: {t['text']}"
            for t in sorted(call.get("transcript", []), key=lambda x: x["idx"])
        )
        user = (
            f"RECIPIENT: {lead['first_name']} {lead['last_name']} ({lead['lead_type']})\n"
            f"CALL WAS HANDED TO A COLLEAGUE: {bool(call.get('escalated'))}\n"
            f"AGREED NEXT STEP: {(call.get('analysis') or {}).get('conversion', {}).get('next_step') or 'none'}\n\n"
            f"PROPERTIES PRESENTED AND THEIR VERIFIED FACTS\n{facts}\n\n"
            f"TRANSCRIPT\n{transcript}"
        )
        raw = await azure_client.complete_json(
            "composer",
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            "followup_message",
            MESSAGE_SCHEMA,
            temperature=0.3,
        )
        data = json.loads(raw)
    else:
        log.warning("no Azure deployment configured - drafting %s offline", call_id)
        data = _offline_draft(lead, call, presented)

    message_id = await next_id("MS", db.messages, "message_id")
    await db.messages.insert_one(
        {
            "message_id": message_id,
            "call_id": call_id,
            "lead_id": lead["lead_id"],
            "whatsapp": {
                "body": data["whatsapp_body"],
                "status": "pending",
                "provider_id": None,
                "sent_at": None,
                "error": None,
            },
            "email": {
                "subject": data["email_subject"],
                "body_text": data["email_body_text"],
                "status": "pending",
                "provider_id": None,
                "sent_at": None,
                "error": None,
            },
            "status": "draft",
            "triggered_by": None,
            "triggered_at": None,
            "created_at": utcnow(),
        }
    )
    log.info("drafted %s for %s", message_id, call_id)
    return message_id
