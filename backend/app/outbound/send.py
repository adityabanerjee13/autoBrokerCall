"""The only code path in this system that sends anything to a customer.

No model can reach it. It is reached by one HTTP POST, from one button, after a
person has read the draft.
"""
import logging

from fastapi import APIRouter, HTTPException
from pymongo import ReturnDocument

from app.db import db, utcnow
from app.models import SendResponse
from app.outbound import email, whatsapp

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.post("/{message_id}/send", response_model=SendResponse)
async def send(message_id: str) -> SendResponse:
    # The status filter is the idempotency guard: a second click lands while
    # the row reads "sending", matches nothing, and 409s - so a double-click
    # sends exactly once. "partial" and "failed" are included so the Retry
    # button in the broker dashboard has something to retry; "sent" is not.
    msg = await db.messages.find_one_and_update(
        {"message_id": message_id, "status": {"$in": ["draft", "partial", "failed"]}},
        {
            "$set": {
                "status": "sending",
                "triggered_by": "broker-demo",
                "triggered_at": utcnow(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if msg is None:
        raise HTTPException(409, "Already sent or not found")

    wa = await whatsapp.send(msg["lead_id"], msg["whatsapp"]["body"])
    em = await email.send(msg["lead_id"], msg["email"]["subject"], msg["email"]["body_text"])

    if wa.ok and em.ok:
        status = "sent"
    elif wa.ok or em.ok:
        status = "partial"
    else:
        status = "failed"

    now = utcnow()
    await db.messages.update_one(
        {"message_id": message_id},
        {
            "$set": {
                "status": status,
                "whatsapp.status": wa.state,
                "whatsapp.provider_id": wa.id,
                "whatsapp.sent_at": now if wa.ok else None,
                "whatsapp.error": wa.error,
                "email.status": em.state,
                "email.provider_id": em.id,
                "email.sent_at": now if em.ok else None,
                "email.error": em.error,
            }
        },
    )
    log.info("message %s -> %s (whatsapp=%s email=%s)", message_id, status, wa.state, em.state)
    return SendResponse(status=status)
