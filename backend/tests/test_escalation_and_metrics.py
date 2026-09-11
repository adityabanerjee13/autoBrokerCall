"""The detector, the handoff line, and the deterministic metrics."""
import pytest

from app.agent.escalation import detect, handoff_message
from app.analysis import metrics
from app.config import policy


@pytest.mark.parametrize(
    "utterance, expected",
    [
        ("the owner said only vegetarian families should be shown the flat",
         "DISCRIMINATORY_FILTER"),
        ("we prefer no bachelors in the building", "DISCRIMINATORY_FILTER"),
        ("can part of the rent be in cash", "CASH_RENT_REQUEST"),
        ("where do I send the token", "PAYMENT_REQUEST"),
        ("I would rather speak to a person", "HUMAN_REQUESTED"),
        ("put me through to your manager", "HUMAN_REQUESTED"),
    ],
)
def test_detector_fires_on_policy_triggers(utterance, expected):
    assert detect(utterance) == expected


@pytest.mark.parametrize(
    "utterance",
    [
        "we need three bedrooms and covered parking",
        "the budget is fifty thousand a month",
        "can we see it on Saturday morning",
        "",
    ],
)
def test_detector_stays_quiet_on_ordinary_conversation(utterance):
    assert detect(utterance) is None


def test_handoff_message_is_the_policy_constant_and_never_generated():
    expected = " ".join(policy()["handoff_message"].split())
    assert handoff_message() == expected
    assert "colleagues should handle directly" in handoff_message()


def test_metrics_on_an_empty_transcript():
    assert metrics.compute([]) == {
        "agent_talk_ratio": 0.0,
        "avg_latency_ms": 0,
        "dead_air_events": 0,
        "turn_count": 0,
    }


def test_metrics_are_derived_from_timestamps_not_guessed():
    # Two 6-word turns: 6 words at 150 wpm = 2400ms of speech each.
    transcript = [
        {"idx": 0, "role": "agent", "text": "one two three four five six", "at_ms": 0},
        {"idx": 1, "role": "lead", "text": "one two three four five six", "at_ms": 3000},
        {"idx": 2, "role": "agent", "text": "one two three four five six", "at_ms": 6400},
    ]
    result = metrics.compute(transcript)

    assert result["turn_count"] == 3
    # Equal speech on both sides once, agent twice: 4800 / 7200.
    assert result["agent_talk_ratio"] == pytest.approx(0.667, abs=0.001)
    # Lead starts at 3000, speaks 2400ms, agent starts at 6400 -> 1000ms latency.
    assert result["avg_latency_ms"] == 1000
    assert result["dead_air_events"] == 0


def test_dead_air_is_counted_when_a_gap_exceeds_the_threshold():
    transcript = [
        {"idx": 0, "role": "lead", "text": "hello", "at_ms": 0},
        {"idx": 1, "role": "agent", "text": "hello", "at_ms": 9000},
    ]
    result = metrics.compute(transcript)
    assert result["dead_air_events"] == 1
    assert result["avg_latency_ms"] > metrics.DEAD_AIR_MS
