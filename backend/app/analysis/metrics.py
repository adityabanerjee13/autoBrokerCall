"""Deterministic call metrics, computed from timestamps.

Never ask a model for talk ratio, latency, dead air or turn count. These are
arithmetic, and a judge that guesses at them is a judge you cannot trust on
anything else.
"""
WORDS_PER_MINUTE = 150
_MS_PER_WORD = 60_000 / WORDS_PER_MINUTE
DEAD_AIR_MS = 3_000


def speaking_ms(text: str) -> float:
    return max(1.0, len(text.split()) * _MS_PER_WORD)


def compute(transcript: list[dict]) -> dict:
    if not transcript:
        return {
            "agent_talk_ratio": 0.0,
            "avg_latency_ms": 0,
            "dead_air_events": 0,
            "turn_count": 0,
        }

    turns = sorted(transcript, key=lambda t: t["idx"])

    agent_ms = sum(speaking_ms(t["text"]) for t in turns if t["role"] == "agent")
    lead_ms = sum(speaking_ms(t["text"]) for t in turns if t["role"] == "lead")
    total_ms = agent_ms + lead_ms

    latencies: list[int] = []
    dead_air = 0
    for prev, curr in zip(turns, turns[1:]):
        gap = curr["at_ms"] - prev["at_ms"] - speaking_ms(prev["text"])
        gap = max(0, int(gap))
        if prev["role"] == "lead" and curr["role"] == "agent":
            latencies.append(gap)
        if gap > DEAD_AIR_MS:
            dead_air += 1

    return {
        "agent_talk_ratio": round(agent_ms / total_ms, 3) if total_ms else 0.0,
        "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
        "dead_air_events": dead_air,
        "turn_count": len(turns),
    }


def signals(transcript: list[dict]) -> list[dict]:
    """The same arithmetic as compute(), kept per turn instead of aggregated.

    The manager drill-down needs to show *where* the latency and the dead air
    were, not just their averages. Deriving both from one function is what stops
    the detail view and the summary row disagreeing - which is exactly the kind
    of discrepancy that makes a reviewer stop trusting the whole dashboard.
    """
    if not transcript:
        return []

    turns = sorted(transcript, key=lambda t: t["idx"])
    out: list[dict] = []
    prev: dict | None = None

    for turn in turns:
        gap: int | None = None
        if prev is not None:
            gap = max(0, int(turn["at_ms"] - prev["at_ms"] - speaking_ms(prev["text"])))

        out.append(
            {
                "idx": turn["idx"],
                "role": turn["role"],
                "text": turn["text"],
                "at_ms": turn["at_ms"],
                # The gap before this turn. None on the first turn, because
                # there is nothing to have waited for.
                "gap_ms": gap,
                # Only a lead->agent gap is the agent being slow. An agent->lead
                # gap is a person thinking, which is not a performance problem.
                "is_agent_latency": bool(
                    prev is not None and prev["role"] == "lead" and turn["role"] == "agent"
                ),
                "dead_air": bool(gap is not None and gap > DEAD_AIR_MS),
                "speaking_ms": int(speaking_ms(turn["text"])),
            }
        )
        prev = turn

    return out
