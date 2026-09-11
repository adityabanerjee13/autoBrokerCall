"""Escalation: two entry points, one exit.

Entry points are the substring detector below (evaluated on each incoming lead
turn, *before* the model is asked to respond) and the agent's own
`escalate_to_human` tool. Both funnel into `perform_handoff`.

There is no transfer, no queue and no SLA in this POC. The handoff line itself
is a constant read from policy.yaml - it is never model-generated.
"""
import logging
import re
from datetime import datetime

from app.config import policy
from app.db import db, utcnow

log = logging.getLogger(__name__)


def handoff_message() -> str:
    """The verbatim line spoken on every escalation. Never generated."""
    return " ".join(policy()["handoff_message"].split())


def detect(text: str) -> str | None:
    """Return an escalation_reason code when a lead turn trips a detector."""
    haystack = text.lower()
    for reason, needles in policy()["detectors"].items():
        for needle in needles:
            if re.search(r"\b" + re.escape(needle.lower()) + r"\b", haystack):
                log.info("escalation detector hit: %s on %r", reason, needle)
                return reason
    return None


async def perform_handoff(
    call_id: str,
    lead_id: str,
    reason: str,
    at_ms: int,
    next_idx: int,
    cancel_speech=None,
) -> dict:
    """Steps 1-5 of the handoff, in order. Step 6 (analysis) is finalize's job.

    Returns the agent transcript turn that was appended, so the caller can
    stream it. The caller hangs up immediately after.
    """
    # 1. cancel in-flight speech
    if cancel_speech is not None:
        try:
            await cancel_speech()
        except Exception:  # a failed barge-in must not block the handoff
            log.exception("could not cancel in-flight speech on %s", call_id)

    # 2. speak the handoff message verbatim
    turn = {"idx": next_idx, "role": "agent", "text": handoff_message(), "at_ms": at_ms}
    now: datetime = utcnow()

    # 3. mark the call
    await db.calls.update_one(
        {"call_id": call_id},
        {
            "$push": {"transcript": turn},
            "$set": {
                "escalated": True,
                "escalation_reason": reason,
                "escalated_at": now,
            },
        },
    )

    # 4. mark the lead
    await db.leads.update_one(
        {"lead_id": lead_id}, {"$set": {"lead_status": "Escalated"}}
    )

    log.info("call %s escalated: %s", call_id, reason)
    # 5. the caller hangs up on return.
    return turn
