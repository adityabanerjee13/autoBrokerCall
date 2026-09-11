"""One agent turn, shared by every runner.

The scripted runner and a dialled VoBiz call must produce the same documents
from the same conversation - that invariant is the whole reason the demo is
trustworthy. So the pieces that actually write those documents live here, and
a runner is only a transport around them.
"""
import json
import logging

from app.agent import guardrail
from app.agent.tools import TOOL_SCHEMAS, ToolContext, execute
from app.analysis.metrics import speaking_ms
from app.db import db
from app.llm import azure_client

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4


class Tape:
    """Appends turns and tool calls to the call document as they happen.

    `at_ms` is the moment a turn *starts*, and the clock then advances by how
    long that utterance takes to speak. metrics.py derives latency and dead air
    from exactly that relationship, so every runner has to honour it or the
    numbers on the manager dashboard are meaningless.
    """

    def __init__(self, call_id: str):
        self.call_id = call_id
        self.idx = 0
        self.elapsed_ms = 0

    def advance(self, ms: int) -> int:
        self.elapsed_ms += ms
        return self.elapsed_ms

    async def say(self, role: str, text: str, advance: bool = True) -> dict:
        """Append one turn at the current clock.

        `advance=False` is for a runner that has a real clock of its own: the
        a live call knows how long the utterance actually took, and
        estimating it from the word count on top of that would count the same
        seconds twice.
        """
        turn = {"idx": self.idx, "role": role, "text": text, "at_ms": self.elapsed_ms}
        self.idx += 1
        if advance:
            self.advance(int(speaking_ms(text)))
        await db.calls.update_one(
            {"call_id": self.call_id}, {"$push": {"transcript": turn}}
        )
        return turn

    async def tool(self, name: str, args: dict, allowed: bool, reason: str | None) -> None:
        await db.calls.update_one(
            {"call_id": self.call_id},
            {
                "$push": {
                    "tool_calls": {
                        "name": name,
                        "args": args,
                        "allowed": allowed,
                        "reason": reason,
                        "at_ms": self.elapsed_ms,
                    }
                }
            },
        )


async def run_tool(name: str, args: dict, ctx: ToolContext, tape: Tape) -> str:
    """Guardrail first, execute second, record either way."""
    escalated = ctx.escalation_reason is not None
    allowed, reason = await guardrail.check(name, args, ctx, escalated)
    await tape.tool(name, args, allowed, reason)
    if not allowed:
        return guardrail.DENIAL_MESSAGE[reason]
    return await execute(name, args, ctx)


async def agent_reply(
    messages: list[dict], ctx: ToolContext, tape: Tape
) -> tuple[str, bool]:
    """One agent turn against the live model. Returns (spoken_text, escalated).

    Runs the model, then routes every proposed tool call through the guardrail
    before executing it. Denials are handed back to the model as tool results
    so it can recover in words rather than by failing.
    """
    for _ in range(MAX_TOOL_ROUNDS):
        resp = await azure_client.complete(
            "agent", messages, tools=TOOL_SCHEMAS, tool_choice="auto", temperature=0.4
        )
        msg = resp.choices[0].message
        calls = msg.tool_calls or []
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {
                            "name": c.function.name,
                            "arguments": c.function.arguments,
                        },
                    }
                    for c in calls
                ]
                or None,
            }
        )
        if not calls:
            return (msg.content or "").strip(), False

        for call in calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = await run_tool(name, args, ctx, tape)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            if ctx.escalation_reason:
                return "", True

    return "", False


def model_available() -> bool:
    return azure_client.available()
