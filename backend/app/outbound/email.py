"""Email provider adapter.

MOCK_OUTBOUND=true logs and returns ok after a short delay.
"""
import asyncio
import logging
import uuid

import httpx

from app.config import settings
from app.db import db
from app.outbound.whatsapp import SendResult

log = logging.getLogger(__name__)


async def send(lead_id: str, subject: str, body_text: str) -> SendResult:
    lead = await db.leads.find_one({"lead_id": lead_id}, {"email": 1, "first_name": 1})
    to = (lead or {}).get("email")
    if not to:
        return SendResult(False, "failed", error="lead has no email address")

    if settings.mock_outbound:
        await asyncio.sleep(0.7)
        log.info("[MOCK EMAIL] to=%s subject=%r", to, subject)
        return SendResult(True, "sent", id=f"mock-em-{uuid.uuid4().hex[:12]}")

    if not settings.email_api_key:
        return SendResult(False, "failed", error="email credentials not configured")

    try:
        async with httpx.AsyncClient(timeout=20) as http:
            resp = await http.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.email_api_key}"},
                json={
                    "from": "Asha <asha@brokeragent.example>",
                    "to": [to],
                    "subject": subject,
                    "text": body_text,
                },
            )
        resp.raise_for_status()
        return SendResult(True, "sent", id=resp.json().get("id"))
    except Exception as exc:
        log.exception("email send failed for %s", lead_id)
        return SendResult(False, "failed", error=str(exc)[:300])
