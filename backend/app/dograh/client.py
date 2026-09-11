"""The outbound half of the Dograh seam.

This module is the only one that holds a Dograh credential or knows the shape
of its API - the same containment rule `llm/azure_client.py` follows for the
model client.

What is deliberately *not* sent over this seam is `lead_memory`. The memory
block is composed into `initial_context` as prose for the agent to read, never
as a field the orchestrator stores or returns - it stays agent-private, which
is the rule `tests/test_invariants.py` has always enforced.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def configured() -> bool:
    return settings.dograh_configured


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "X-API-Key": settings.dograh_api_key,
                "Content-Type": "application/json",
            },
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ------------------------------------------------------------------- dialling

async def place_call(*, to: str, call_id: str, context: dict[str, Any]) -> int:
    """Hand one call to Dograh. Returns its `workflow_run_id`.

    Everything after this arrives as a tool call or a webhook, so `call_id`
    rides along in `initial_context` - it is how those endpoints map a Dograh
    run back to the row this app is grading.

    A 2xx means the run was created, not that anyone answered.
    """
    if not configured():
        raise RuntimeError("Dograh is not configured")

    body: dict[str, Any] = {
        "phone_number": to,
        "initial_context": {**context, "broker_call_id": call_id},
    }
    if settings.dograh_telephony_configuration_id is not None:
        body["telephony_configuration_id"] = settings.dograh_telephony_configuration_id
    if settings.dograh_from_phone_number_id is not None:
        body["from_phone_number_id"] = settings.dograh_from_phone_number_id

    response = await _http().post(settings.dograh_trigger_url, json=body)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Dograh refused the call ({response.status_code}): "
            f"{response.text[:300] or '(no body)'}"
        )

    data = response.json()
    run_id = data.get("workflow_run_id")
    if run_id is None:
        raise RuntimeError(f"Dograh returned no workflow_run_id: {data}")

    log.info("dograh queued %s -> %s (run=%s)", call_id, to, run_id)
    return int(run_id)


async def get_run(run_id: int) -> dict[str, Any]:
    """Fetch one run: status, dispositions, recording and transcript URLs."""
    if not configured():
        raise RuntimeError("Dograh is not configured")
    response = await _http().get(
        f"{settings.dograh_api_base.rstrip('/')}/api/v1/runs/{run_id}"
    )
    response.raise_for_status()
    return response.json()


async def signed_url(key: str) -> str:
    """Turn a Dograh storage key into a URL that can actually be fetched.

    The webhook sends `transcripts/695189.txt` - an S3 key, not a URL. Handing
    that to an HTTP client raises ConnectError, which is exactly how a finished
    call came to be graded with zero turns while its transcript sat in storage.
    """
    response = await _http().get(
        f"{settings.dograh_api_base.rstrip('/')}/api/v1/s3/signed-url",
        params={"key": key},
    )
    response.raise_for_status()
    data = response.json()
    return data.get("url") or data.get("signed_url") or ""


# `[2026-09-11T02:18:11.191+00:00] assistant: Hi, am I speaking with Aditya?`
TRANSCRIPT_LINE = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\s*(?P<role>[A-Za-z_]+)\s*:\s*(?P<text>.*)$"
)


def parse_transcript(body: str) -> list[dict[str, Any]]:
    """Dograh publishes a plain-text transcript, one utterance per line.

    Timestamps are absolute and ISO-8601; the tape wants milliseconds from the
    first utterance, because that is what `analysis/metrics.py` measures
    latency and dead air against.
    """
    turns: list[dict[str, Any]] = []
    first: datetime | None = None

    for raw_line in body.splitlines():
        match = TRANSCRIPT_LINE.match(raw_line.strip())
        if not match:
            continue
        text = match.group("text").strip()
        if not text:
            continue

        at_ms = len(turns) * 3000
        try:
            stamp = datetime.fromisoformat(match.group("ts"))
            first = first or stamp
            at_ms = max(0, int((stamp - first).total_seconds() * 1000))
        except ValueError:
            # An unparseable timestamp must not cost us the utterance.
            pass

        turns.append(
            {"role": match.group("role").lower(), "text": text, "at_ms": at_ms}
        )
    return turns


async def fetch_transcript(url_or_key: str) -> list[dict[str, Any]]:
    """Pull the transcript Dograh published for a finished run.

    Accepts either an absolute URL or a storage key, because Dograh's webhook
    sends the latter and its API hands out the former.
    """
    if not url_or_key:
        return []

    try:
        target = url_or_key
        if not target.startswith(("http://", "https://")):
            target = await signed_url(target)
        if not target:
            return []

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(target)
        response.raise_for_status()
    except Exception:
        log.exception("could not fetch transcript from %s", url_or_key)
        return []

    body = response.text
    turns = parse_transcript(body)
    if turns:
        return turns

    # Older runs published JSON. Accept it rather than lose the call.
    try:
        payload = response.json()
    except ValueError:
        log.warning("transcript for %s parsed to nothing (%d bytes)", url_or_key, len(body))
        return []

    if isinstance(payload, dict):
        for key in ("transcript", "turns", "messages"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return []
    return payload if isinstance(payload, list) else []
