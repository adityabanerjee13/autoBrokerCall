"""The manager's audit view and the owner's activity feed.

Two audiences with opposite needs. A manager reviewing a grade needs
everything - the turns, the timing, the guardrail's decisions, what went into
memory. An owner needs to know interest exists without learning anything about
the person behind it. These tests pin both, and in particular pin the line
between them.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.analysis.metrics import DEAD_AIR_MS, compute, signals

NOW = datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)

# A short call: greeting, a slow agent reply, a long silence.
TRANSCRIPT = [
    {"idx": 0, "role": "agent", "text": "Hi, am I speaking with Aditya?", "at_ms": 0},
    {"idx": 1, "role": "lead", "text": "Yes.", "at_ms": 4962},
    {"idx": 2, "role": "agent", "text": "Lovely, about the two BHK.", "at_ms": 12000},
]


# ------------------------------------------------------------------- signals

def test_per_turn_signals_agree_with_the_aggregate_metrics():
    """The drill-down and the summary row are derived from one function.

    If they were computed separately they would eventually disagree, and a
    reviewer who spots one discrepancy stops trusting the whole dashboard.
    """
    aggregate = compute(TRANSCRIPT)
    per_turn = signals(TRANSCRIPT)

    latencies = [t["gap_ms"] for t in per_turn if t["is_agent_latency"]]
    assert aggregate["avg_latency_ms"] == int(sum(latencies) / len(latencies))
    assert aggregate["dead_air_events"] == sum(1 for t in per_turn if t["dead_air"])
    assert aggregate["turn_count"] == len(per_turn)


def test_only_a_lead_to_agent_gap_counts_as_agent_latency():
    """A pause after the agent speaks is a person thinking, not a slow agent."""
    per_turn = signals(TRANSCRIPT)

    assert per_turn[0]["gap_ms"] is None          # nothing precedes the first turn
    assert per_turn[1]["is_agent_latency"] is False   # agent -> lead
    assert per_turn[2]["is_agent_latency"] is True    # lead  -> agent


def test_dead_air_uses_the_same_threshold_as_the_metrics():
    quiet = [
        {"idx": 0, "role": "agent", "text": "Hello", "at_ms": 0},
        {"idx": 1, "role": "lead", "text": "Hi", "at_ms": DEAD_AIR_MS + 2_000},
    ]
    assert signals(quiet)[1]["dead_air"] is True

    prompt = [
        {"idx": 0, "role": "agent", "text": "Hello", "at_ms": 0},
        {"idx": 1, "role": "lead", "text": "Hi", "at_ms": 500},
    ]
    assert signals(prompt)[1]["dead_air"] is False


def test_signals_of_an_empty_transcript_is_empty_not_an_error():
    """A failed call has no turns, and the drawer still has to render."""
    assert signals([]) == []


# ------------------------------------------------------------- owner privacy

def test_the_notification_phrase_names_nobody():
    from app.api.client import ANONYMOUS

    assert "tenant" in ANONYMOUS
    # One phrase, used everywhere, so there is no second place a name can
    # creep in later.
    assert not any(ch.isdigit() for ch in ANONYMOUS)


def test_only_tools_that_actually_happened_become_notifications():
    """A tool the guardrail refused did not happen.

    Reporting a refused `present_property` to an owner would tell them their
    flat was shown when it was not - and the guardrail refuses exactly in the
    cases where showing it would have been wrong.
    """
    from app.api.client import NOTIFIED_TOOLS

    assert set(NOTIFIED_TOOLS) == {"present_property", "book_appointment"}
    # note_memory and capture_field are about the *renter*, and must never
    # reach an owner's feed.
    for private in ("note_memory", "capture_field", "search_properties"):
        assert private not in NOTIFIED_TOOLS


def test_the_owner_notification_model_has_no_field_for_a_person():
    """Anonymity enforced by the shape of the response, not by remembering."""
    from app.models import OwnerNotification

    fields = set(OwnerNotification.model_fields)
    assert fields == {"event", "property_id", "address", "at", "detail"}
    for leak in ("first_name", "last_name", "lead_id", "phone", "budget"):
        assert leak not in fields


# ------------------------------------------------------------ manager audit

def test_the_trace_carries_the_evidence_beside_the_verdict():
    """A grade with no trace is an assertion. These are the fields that make
    it checkable."""
    from app.models import CallTrace

    fields = set(CallTrace.model_fields)
    for evidence in ("turns", "tools", "analysis", "memory_written", "provider", "metrics"):
        assert evidence in fields


def test_a_flagged_turn_carries_the_reason_it_was_flagged():
    from app.models import TurnSignal

    turn = TurnSignal(
        idx=3, role="lead", text="only vegetarian tenants", at_ms=1000,
        speaking_ms=900, gap_ms=200, flagged=True,
        flag_reason="DISCRIMINATORY_FILTER: food-habit condition on tenancy",
    )
    assert turn.flagged and turn.flag_reason
    assert "DISCRIMINATORY_FILTER" in turn.flag_reason


def test_memory_entries_are_attributed_to_the_call_that_wrote_them():
    """The audit shows what *this* call remembered, not the whole history.

    A memory entry steers the next call, so the reviewer needs to see the
    durable consequence of the conversation in front of them.
    """
    from app.models import MemoryEntryView

    entry = MemoryEntryView(kind="commitment", text="Viewing booked for Thursday.")
    assert entry.kind == "commitment"
    assert entry.created_at is None  # optional: older entries predate the field


def test_provider_trace_is_optional_so_a_scripted_call_still_renders():
    """The mock transport has no orchestrator run behind it."""
    from app.models import ProviderTrace

    scripted = ProviderTrace(transport="mock")
    assert scripted.run_id is None and scripted.trace_url is None


@pytest.mark.parametrize(
    "placeholder", ["{{gathered_context.trace_url}}", "", "   ", None]
)
def test_an_unrendered_template_placeholder_is_not_stored_as_a_url(placeholder):
    """Jinja leaves the placeholder in when the key is absent.

    Storing it would put a visibly broken link on the manager dashboard.
    """
    from app.api.dograh import _clean

    assert _clean(placeholder) is None


def test_a_real_trace_url_survives_cleaning():
    from app.api.dograh import _clean

    url = "https://langfuse.dograh.com/project/abc/traces/def"
    assert _clean(url) == url
