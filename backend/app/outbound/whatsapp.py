"""WhatsApp provider adapter.

MOCK_OUTBOUND=true logs and returns ok after a short delay, so the demo never
sends a real message by accident.
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass

import httpx

from app.config import settings
from app.db import db

log = logging.getLogger(__name__)


@dataclass
class SendResult:
    ok: bool
    state: str          # "sent" | "failed"
    id: str | None = None
    error: str | None = None


async def send(lead_id: str, body: str) -> SendResult:
    lead = await db.leads.find_one({"lead_id": lead_id}, {"phone": 1})
    to = (lead or {}).get("phone")
    if not to:
        return SendResult(False, "failed", error="lead has no phone number")

    if settings.mock_outbound:
        await asyncio.sleep(0.7)
        log.info("[MOCK WHATSAPP] to=%s body=%r", to, body)
        return SendResult(True, "sent", id=f"mock-wa-{uuid.uuid4().hex[:12]}")

    if not (settings.whatsapp_token and settings.whatsapp_phone_number_id):
        return SendResult(False, "failed", error="whatsapp credentials not configured")

    url = f"https://graph.facebook.com/v20.0/{settings.whatsapp_phone_number_id}/messages"
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            resp = await http.post(
                url,
                headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to.lstrip("+"),
                    "type": "text",
                    "text": {"body": body},
                },
            )
        resp.raise_for_status()
        return SendResult(True, "sent", id=resp.json()["messages"][0]["id"])
    except Exception as exc:
        log.exception("whatsapp send failed for %s", lead_id)
        return SendResult(False, "failed", error=str(exc)[:300])
