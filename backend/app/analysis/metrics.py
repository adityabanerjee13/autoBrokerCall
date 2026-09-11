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
