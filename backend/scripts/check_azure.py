"""Verify the Azure AI Foundry setup before running a call.

Exercises exactly what the app does, in the order it does it:
  1. a plain completion on the `agent` deployment
  2. a tool call on the `agent` deployment
  3. a strict json_schema completion on `analyzer` (the safety track's schema)
  4. a strict json_schema completion on `composer`

Run:  .venv/Scripts/python scripts/check_azure.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.tools import TOOL_SCHEMAS  # noqa: E402
from app.analysis.schemas import MESSAGE_SCHEMA, SAFETY_SCHEMA  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import azure_client  # noqa: E402

OK, BAD = "  OK  ", " FAIL "


def line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f" - {detail}" if detail else ""))


async def check_completion() -> bool:
    try:
        resp = await azure_client.complete(
            "agent",
            [{"role": "user", "content": "Reply with the single word: ready"}],
            max_tokens=10,
        )
        line(OK, f"agent deployment '{settings.azure_deployment_agent}'",
             repr((resp.choices[0].message.content or "").strip()))
        return True
    except Exception as exc:
        line(BAD, f"agent deployment '{settings.azure_deployment_agent}'", str(exc)[:400])
        return False


async def check_tools() -> bool:
    try:
        resp = await azure_client.complete(
            "agent",
            [
                {"role": "system", "content": "You are on a call. Record facts as they are said."},
                {"role": "user", "content": "My budget is fifty thousand rupees a month."},
            ],
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            max_tokens=200,
        )
        calls = resp.choices[0].message.tool_calls or []
        if not calls:
            line(BAD, "tool calling", "model answered without calling capture_field")
            return False
        line(OK, "tool calling", ", ".join(c.function.name for c in calls))
        return True
    except Exception as exc:
        line(BAD, "tool calling", str(exc)[:400])
        return False


async def check_structured(role: str, deployment: str, name: str, schema: dict) -> bool:
    """The most likely thing to break: strict json_schema needs gpt-4o >= 2024-08-06."""
    try:
        raw = await azure_client.complete_json(
            role,
            [
                {"role": "system", "content": "Return the smallest valid object for the schema."},
                {"role": "user", "content": "AGENT: Hello.\nLEAD: Not interested, thanks."},
            ],
            name,
            schema,
            temperature=0,
        )
        json.loads(raw)
        line(OK, f"{role} structured output '{deployment}'", f"schema {name} accepted")
        return True
    except Exception as exc:
        line(BAD, f"{role} structured output '{deployment}'", str(exc)[:400])
        return False


async def main() -> int:
    print(f"endpoint: {settings.azure_openai_endpoint or '(unset)'}")
    print(f"api version: {settings.azure_openai_api_version}\n")

    if not azure_client.available():
        line(BAD, "configuration",
             "AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY are not set in backend/.env")
        print("\nThe app will keep running on its offline fallbacks until these are set.")
        return 1

    results = [
        await check_completion(),
        await check_tools(),
        await check_structured(
            "analyzer", settings.azure_deployment_analyzer, "safety_track", SAFETY_SCHEMA
        ),
        await check_structured(
            "composer", settings.azure_deployment_composer, "followup_message", MESSAGE_SCHEMA
        ),
    ]

    failed = results.count(False)
    print()
    if failed:
        print(f"{failed} check(s) failed. The app falls back to offline stand-ins for "
              "anything that cannot reach a deployment.")
        return 1
    print("All model checks passed. Restart uvicorn and /api/health will report "
          "llm_configured: true.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
