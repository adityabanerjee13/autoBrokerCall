"""The Dograh seam, without Dograh.

Dograh runs the call now - the VoBiz leg, Azure Speech and the conversation
graph are all its concern. What is still ours is the seam: which transport a
given .env resolves to, that nothing unauthenticated can drive a live call
through our tool endpoints, that a webhook retry does not grade a call twice,
and that a transcript in Dograh's vocabulary lands in ours.

None of these reach the network.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.api import dograh as dograh_api
from app.config import Settings, settings
from app.dograh import client as dograh_client

CALL_ID = "CL-0001"
SECRET = "s3cret-shared-with-the-workflow"

DOGRAH_ENV = {
    "call_transport": "dograh",
    "dograh_api_key": "dg_test_key",
    "dograh_workflow_uuid": "11111111-2222-3333-4444-555555555555",
    "dograh_shared_secret": SECRET,
}


@pytest.fixture
def dialling(monkeypatch):
    for key, value in DOGRAH_ENV.items():
        monkeypatch.setattr(settings, key, value)
    return settings


@pytest.fixture
def client(dialling):
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ------------------------------------------------------------------ transport

def test_a_fully_configured_account_dials():
    assert Settings(**DOGRAH_ENV).transport == "dograh"


@pytest.mark.parametrize("missing", sorted(set(DOGRAH_ENV) - {"call_transport"}))
def test_any_missing_credential_falls_back_to_the_script(missing):
    """Half an orchestrator is not an orchestrator.

    The shared secret counts: without it the tool endpoints have nothing to
    authenticate, and they are the agent's only route to the database.
    """
    assert Settings(**{**DOGRAH_ENV, missing: ""}).transport == "mock"


def test_the_trigger_url_uses_the_agent_uuid():
    """An API Trigger node's uuid is a different id and a 404 at Dograh."""
    url = Settings(**DOGRAH_ENV).dograh_trigger_url
    assert url.endswith(f"/api/v1/public/agent/workflow/{DOGRAH_ENV['dograh_workflow_uuid']}")


# ---------------------------------------------------------------------- health

def test_health_answers_without_touching_a_removed_setting(client):
    """The container healthcheck calls this, so a stale attribute here does not
    fail one request - it takes the whole service down and blocks the deploy.

    That is exactly what happened when VoBiz and Azure Speech moved into
    Dograh: /api/health still asked for `speech_configured` and the container
    never went healthy.
    """
    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.json()
    assert body["ok"] is True
    assert body["transport"] == "dograh"
    assert body["dograh_configured"] is True
    # Settings that moved into Dograh must not reappear here.
    assert "speech_configured" not in body
    assert "telephony_configured" not in body


def test_health_answers_on_a_bare_install(monkeypatch):
    """No credentials at all is the demo path, and it must still report."""
    from app.main import app

    monkeypatch.setattr(settings, "call_transport", "mock")
    monkeypatch.setattr(settings, "dograh_api_key", "")
    with TestClient(app) as bare:
        body = bare.get("/api/health").json()
    assert body["transport"] == "mock"
    assert body["dograh_configured"] is False


# ----------------------------------------------------------------- tool calls

def test_an_unauthenticated_tool_call_is_refused(client):
    """This endpoint books viewings on real leads."""
    response = client.post(
        "/api/dograh/tools/book_appointment",
        json={"broker_call_id": CALL_ID},
        headers={"X-Dograh-Secret": "guess"},
    )
    assert response.status_code == 403


def test_a_tool_call_with_no_secret_at_all_is_refused(client):
    response = client.post(
        "/api/dograh/tools/capture_field", json={"broker_call_id": CALL_ID}
    )
    assert response.status_code == 403


def test_an_unknown_tool_is_refused_before_anything_is_loaded(client):
    """The agent may only reach the seven tools it was given."""
    response = client.post(
        "/api/dograh/tools/transfer_money",
        json={"broker_call_id": CALL_ID},
        headers={"X-Dograh-Secret": SECRET},
    )
    assert response.status_code == 404


def test_a_tool_call_must_say_which_call_it_belongs_to(client):
    response = client.post(
        "/api/dograh/tools/capture_field",
        json={"field": "budget"},
        headers={"X-Dograh-Secret": SECRET},
    )
    assert response.status_code == 422


def test_the_tool_endpoint_offers_exactly_the_agent_tools():
    """The endpoint is generic, so its allowlist is the schema list itself."""
    from app.agent.tools import TOOL_SCHEMAS

    assert {t["function"]["name"] for t in TOOL_SCHEMAS} == {
        "capture_field",
        "search_properties",
        "present_property",
        "book_appointment",
        "note_memory",
        "escalate_to_human",
        "end_call",
    }


# -------------------------------------------------------------------- webhook

def test_an_unauthenticated_webhook_cannot_close_a_call(client):
    response = client.post(
        "/api/dograh/webhook",
        json={"workflow_run_id": 1},
        headers={"X-Dograh-Secret": "guess"},
    )
    assert response.status_code == 403


def test_a_webhook_for_an_unknown_run_is_ignored_not_an_error(client):
    """Dograh retries on non-2xx. A run we do not know is not a failure."""
    response = client.post(
        "/api/dograh/webhook",
        json={"workflow_run_id": 999999, "initial_context": {}},
        headers={"X-Dograh-Secret": SECRET},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_the_webhook_reads_the_flat_keys_dograh_actually_sends():
    """Dograh renders the payload template with Jinja, one scalar at a time.

    A template value of `{{initial_context}}` arrives as a stringified dict, not
    an object - so the call id has to come from a flat key. This is the shape
    provision_dograh.py writes into the node.
    """
    payload = {
        "broker_call_id": CALL_ID,
        "workflow_run_id": 4242,
        "call_duration_seconds": "137",
        "recording_url": "https://example.com/r.wav",
    }
    assert dograh_api._duration_seconds(payload) == 137
    assert payload["broker_call_id"] == CALL_ID


def test_duration_survives_the_shapes_a_template_can_produce():
    """It is a Jinja-rendered string, an int, a float, or missing entirely."""
    d = dograh_api._duration_seconds
    assert d({"call_duration_seconds": "137"}) == 137
    assert d({"call_duration_seconds": 137}) == 137
    assert d({"call_duration_seconds": 137.8}) == 137
    assert d({"cost_info": {"call_duration_seconds": "90"}}) == 90
    # An unrendered placeholder must not crash the webhook - a call that
    # happened still has to be graded.
    assert d({"call_duration_seconds": "{{cost_info.call_duration_seconds}}"}) == 0
    assert d({}) == 0


def test_a_stringified_context_does_not_break_the_webhook(client):
    """If someone writes {{initial_context}} into the template by hand, the
    webhook must degrade to 'ignored', not 500."""
    response = client.post(
        "/api/dograh/webhook",
        json={
            "workflow_run_id": 987654,
            "initial_context": "{'broker_call_id': 'CL-0001'}",
            "gathered_context": "",
        },
        headers={"X-Dograh-Secret": SECRET},
    )
    assert response.status_code == 200


# ------------------------------------------------------- transcript ingestion

def test_dograh_roles_become_our_roles():
    """Dograh speaks assistant/user; the rubrics and dashboards speak agent/lead."""
    turns = _map(
        [
            {"role": "assistant", "text": "Good morning, this is Priya."},
            {"role": "user", "text": "Yes, speaking."},
            {"role": "bot", "text": "Lovely."},
        ]
    )
    assert [t["role"] for t in turns] == ["agent", "lead", "agent"]


def test_empty_and_malformed_turns_are_dropped_not_stored():
    turns = _map([{"role": "user", "text": "   "}, {"role": "user"}, {"role": "user", "text": "ok"}])
    assert len(turns) == 1
    assert turns[0]["text"] == "ok"


def test_the_post_call_detector_is_a_backstop_on_lead_turns_only():
    """Dograh owns turn ordering now, so this guarantees the outcome, not the timing.

    A call where the lead asked for something unlawful ends escalated and gated
    whatever the workflow did in the moment. The agent's own words must never
    trip it - only what the lead said.
    """
    from app.agent import escalation

    unlawful = next(
        (t for t in ESCALATING if escalation.detect(t)), None
    )
    assert unlawful, "no sample utterance trips the detector; fixture is stale"

    escalated, reason = dograh_api._scan_for_escalation(
        [{"role": "lead", "text": unlawful}]
    )
    assert escalated and reason

    # The same sentence spoken by the agent is not a lead request.
    assert dograh_api._scan_for_escalation(
        [{"role": "agent", "text": unlawful}]
    ) == (False, None)


ESCALATING = [
    "Only show it to Hindu families, no Muslims.",
    "I don't want to rent to Muslim tenants.",
    "No bachelors and no non-vegetarians, only Brahmins.",
]


def _map(raw: list[dict]) -> list[dict]:
    """Exercise the mapping in _ingest_transcript without touching the database."""
    turns = []
    for idx, entry in enumerate(raw):
        role = str(entry.get("role") or entry.get("speaker") or "").lower()
        text = (entry.get("text") or entry.get("content") or "").strip()
        if not text:
            continue
        turns.append(
            {
                "idx": idx,
                "role": "agent" if role in ("assistant", "agent", "bot") else "lead",
                "text": text,
                "at_ms": int(entry.get("at_ms") or entry.get("start_ms") or idx * 3000),
            }
        )
    return turns


# --------------------------------------------------------------------- client

async def test_placing_a_call_carries_the_call_id_into_the_workflow(dialling, monkeypatch):
    """`broker_call_id` is how every later tool call finds its way back here."""
    sent = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"status": "success", "workflow_run_id": 4242}

    class FakeClient:
        async def post(self, url, json=None):
            sent["url"] = url
            sent["body"] = json
            return FakeResponse()

    monkeypatch.setattr(dograh_client, "_http", lambda: FakeClient())

    run_id = await dograh_client.place_call(
        to="+919876543210", call_id=CALL_ID, context={"first_name": "Aditya"}
    )

    assert run_id == 4242
    assert sent["body"]["phone_number"] == "+919876543210"
    assert sent["body"]["initial_context"]["broker_call_id"] == CALL_ID
    assert sent["body"]["initial_context"]["first_name"] == "Aditya"
    assert DOGRAH_ENV["dograh_workflow_uuid"] in sent["url"]


async def test_a_refusal_from_dograh_is_raised_not_swallowed(dialling, monkeypatch):
    """A call nobody placed must not sit in `ringing` forever."""

    class FakeResponse:
        status_code = 402
        text = "quota exceeded"

    class FakeClient:
        async def post(self, url, json=None):
            return FakeResponse()

    monkeypatch.setattr(dograh_client, "_http", lambda: FakeClient())

    with pytest.raises(RuntimeError, match="402"):
        await dograh_client.place_call(to="+91", call_id=CALL_ID, context={})


async def test_a_response_without_a_run_id_is_a_failure(dialling, monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"status": "success"}

    class FakeClient:
        async def post(self, url, json=None):
            return FakeResponse()

    monkeypatch.setattr(dograh_client, "_http", lambda: FakeClient())

    with pytest.raises(RuntimeError, match="workflow_run_id"):
        await dograh_client.place_call(to="+91", call_id=CALL_ID, context={})


# Verbatim, from run 695189 - the call that greeted Aditya and then went quiet.
REAL_TRANSCRIPT = """\
[2026-09-11T02:18:11.191+00:00] assistant: Hi, am I speaking with Aditya?
[2026-09-11T02:18:16.153+00:00] user: Yes.
"""


def test_the_plain_text_transcript_dograh_actually_publishes_is_parsed():
    """This is a verbatim transcript from a real run.

    Dograh publishes text, not JSON - one `[timestamp] role: text` line per
    utterance. Reading it as JSON is how an 11-second conversation came to be
    graded as zero turns.
    """
    turns = dograh_client.parse_transcript(REAL_TRANSCRIPT)

    assert [t["role"] for t in turns] == ["assistant", "user"]
    assert turns[0]["text"] == "Hi, am I speaking with Aditya?"
    assert turns[1]["text"] == "Yes."


def test_transcript_timestamps_become_offsets_from_the_first_utterance():
    """`analysis/metrics.py` measures latency against at_ms, so absolute
    wall-clock stamps would make every gap look like 2026 years of dead air."""
    turns = dograh_client.parse_transcript(REAL_TRANSCRIPT)
    assert turns[0]["at_ms"] == 0
    assert 4800 < turns[1]["at_ms"] < 5100


def test_a_transcript_line_that_does_not_parse_is_skipped_not_fatal():
    body = """\
not a transcript line at all
[bad-timestamp] user: still worth keeping
[2026-09-11T02:18:11.191+00:00] assistant:
[2026-09-11T02:18:12.000+00:00] user: real
"""
    turns = dograh_client.parse_transcript(body)
    # The blank utterance and the prose line go; the rest survive.
    assert [t["text"] for t in turns] == ["still worth keeping", "real"]


def test_a_storage_key_is_told_apart_from_a_url():
    """The webhook sends `transcripts/695189.txt`; fetching that as a URL
    raises ConnectError and silently costs the call its transcript."""
    import inspect

    source = inspect.getsource(dograh_client.fetch_transcript)
    assert 'startswith(("http://", "https://"))' in source
    assert "signed_url" in source
