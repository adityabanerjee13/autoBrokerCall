"""Create brokerAgent's tools in Dograh, so nobody has to type them in.

Seven tools, each with its parameters, its description and the shared-secret
header - that is a lot of form-filling to do by hand, and a typo in any of it
surfaces as an agent that quietly never calls a tool. This creates them through
Dograh's REST API instead, from the same `TOOL_SCHEMAS` the scripted runner
uses, so the two can never drift.

    python scripts/provision_dograh.py            # show what would be created
    python scripts/provision_dograh.py --apply    # create them

Re-running is safe: a tool whose name already exists is updated, not duplicated.

What this does NOT do, because Dograh has no API for it: attach the tools to
your conversation nodes. Do that last, in the workflow editor - a tool that
exists but is unattached is invisible to the agent, with no error anywhere.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.agent.tools import TOOL_LEAD_TYPES, TOOL_SCHEMAS  # noqa: E402
from app.config import settings  # noqa: E402

OK, BAD, SKIP = "  OK  ", " FAIL ", " SKIP "

# Dograh injects this from call context rather than asking the model for it.
# Made a preset parameter, not a model parameter, for two reasons: the model
# cannot get it wrong, and it never appears in the tool's function signature
# where it would invite the agent to invent one.
PRESET_CALL_ID = {
    "name": "broker_call_id",
    "type": "string",
    "value_template": "{{initial_context.broker_call_id}}",
    "required": True,
}

# Tool timeouts. A tool call happens mid-sentence on a live phone call, so the
# budget is "before the silence gets awkward", not "before the request times
# out". search_properties touches the database hardest.
TIMEOUT_MS = {"search_properties": 6000}
DEFAULT_TIMEOUT_MS = 4000

ICONS = {
    "capture_field": ("clipboard-list", "#8a6412"),
    "search_properties": ("search", "#146b64"),
    "present_property": ("home", "#146b64"),
    "book_appointment": ("calendar-check", "#146b64"),
    "note_memory": ("brain", "#8a6412"),
    "escalate_to_human": ("phone-forwarded", "#9c4526"),
    "end_call": ("phone-off", "#5b6672"),
}


def line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f" - {detail}" if detail else ""))


def _json_type(spec: dict) -> str:
    """Map an OpenAI tool schema type onto Dograh's parameter types."""
    raw = spec.get("type")
    if raw in ("string", "number", "boolean", "object", "array"):
        return raw
    if raw == "integer":
        return "number"
    # `capture_field.value` is deliberately untyped - it carries a number, a
    # string or an array depending on the field. String is the honest default;
    # the description tells the agent what to actually put there.
    return "string"


def build_tool(schema: dict) -> dict:
    """One CreateToolRequest body, from one of our tool schemas."""
    fn = schema["function"]
    name = fn["name"]
    params = fn.get("parameters") or {}
    props = params.get("properties") or {}
    required = set(params.get("required") or [])

    parameters = [
        {
            "name": pname,
            "type": _json_type(pspec),
            "description": pspec.get("description")
            or f"{pname.replace('_', ' ')} for {name}",
            "required": pname in required,
        }
        for pname, pspec in props.items()
    ]

    lead_types = sorted(TOOL_LEAD_TYPES.get(name, []))
    description = fn.get("description", "")
    if lead_types and set(lead_types) != {"renter", "lender"}:
        description += f" Only valid on a {'/'.join(lead_types)} call."

    icon, colour = ICONS.get(name, ("globe", "#3B82F6"))

    return {
        "name": name,
        "description": description,
        "category": "http_api",
        "icon": icon,
        "icon_color": colour,
        # HttpApiToolDefinition is {schema_version, type, config} - the HTTP
        # details nest under `config`, they are not siblings of `type`.
        "definition": {
            "schema_version": 1,
            "type": "http_api",
            "config": {
                "method": "POST",
                "url": f"{settings.public_base_url.rstrip('/')}/api/dograh/tools/{name}",
                "headers": {"X-Dograh-Secret": settings.dograh_shared_secret},
                "parameters": parameters,
                "preset_parameters": [PRESET_CALL_ID],
                "timeout_ms": TIMEOUT_MS.get(name, DEFAULT_TIMEOUT_MS),
            },
        },
    }


def webhook_hint() -> dict:
    """What to put in the Webhook node. Field names match Dograh's own.

    Every value is a *scalar leaf*. Dograh renders this template with Jinja
    against the run context, so `{{initial_context}}` on its own would arrive
    as a stringified dict rather than an object - which is exactly the kind of
    thing that works in a test and then loses a real call's transcript.
    """
    return {
        "name": "brokerAgent",
        "http_method": "POST",
        "endpoint_url": f"{settings.public_base_url.rstrip('/')}/api/dograh/webhook",
        "custom_headers": {"X-Dograh-Secret": settings.dograh_shared_secret},
        "payload_template": {
            "broker_call_id": "{{initial_context.broker_call_id}}",
            "workflow_run_id": "{{workflow_run_id}}",
            "call_duration_seconds": "{{cost_info.call_duration_seconds}}",
            "call_disposition": "{{gathered_context.call_disposition}}",
            "call_status": "{{gathered_context.call_status}}",
            "recording_url": "{{recording_url}}",
            "transcript_url": "{{transcript_url}}",
        },
    }


async def existing_tools(client: httpx.AsyncClient) -> dict[str, str]:
    """name -> uuid, so a second run updates instead of duplicating."""
    response = await client.get("/api/v1/tools/")
    response.raise_for_status()
    rows = response.json()
    rows = rows if isinstance(rows, list) else rows.get("items", [])
    return {r["name"]: r.get("uuid") or r.get("tool_uuid") for r in rows if r.get("name")}


async def apply(client: httpx.AsyncClient, bodies: list[dict]) -> int:
    try:
        seen = await existing_tools(client)
    except Exception as exc:
        line(BAD, "list existing tools", str(exc)[:200])
        return 1

    failed = 0
    for body in bodies:
        name = body["name"]
        uuid = seen.get(name)
        try:
            if uuid:
                response = await client.put(f"/api/v1/tools/{uuid}", json=body)
                verb = "updated"
            else:
                response = await client.post("/api/v1/tools/", json=body)
                verb = "created"
            if response.status_code >= 400:
                line(BAD, name, f"{response.status_code}: {response.text[:200]}")
                failed += 1
                continue
            line(OK, name, verb)
        except Exception as exc:
            line(BAD, name, str(exc)[:200])
            failed += 1
    return failed


async def main() -> int:
    do_apply = "--apply" in sys.argv

    print(f"Dograh API      : {settings.dograh_api_base}")
    print(f"Tool endpoint   : {settings.public_base_url or '(PUBLIC_BASE_URL not set)'}/api/dograh/tools/<name>")
    print(f"Shared secret   : {'set' if settings.dograh_shared_secret else '(not set)'}")
    print()

    missing = [
        n for n, v in (
            ("PUBLIC_BASE_URL", settings.public_base_url),
            ("DOGRAH_SHARED_SECRET", settings.dograh_shared_secret),
        ) if not v
    ]
    if missing:
        line(BAD, "configuration", f"{', '.join(missing)} must be set first")
        return 1

    bodies = [build_tool(s) for s in TOOL_SCHEMAS]

    if not do_apply:
        print("Dry run. These seven tools would be created:\n")
        for body in bodies:
            d = body["definition"]["config"]
            names = [p["name"] for p in d["parameters"]]
            print(f"  {body['name']}")
            print(f"      POST {d['url']}")
            print(f"      params  : {', '.join(names) or '(none)'}")
            print(f"      preset  : broker_call_id <- {{{{initial_context.broker_call_id}}}}")
            print(f"      timeout : {d['timeout_ms']}ms")
        print()
        print("Webhook node (create this by hand in the workflow editor):")
        print(json.dumps(webhook_hint(), indent=2))
        print()
        print("Re-run with --apply to create them.")
        return 0

    if not settings.dograh_api_key:
        line(BAD, "DOGRAH_API_KEY", "not set - Settings -> API Keys in Dograh")
        return 1

    async with httpx.AsyncClient(
        base_url=settings.dograh_api_base.rstrip("/"),
        timeout=30.0,
        headers={
            "X-API-Key": settings.dograh_api_key,
            "Content-Type": "application/json",
        },
    ) as client:
        failed = await apply(client, bodies)

    print()
    if failed:
        print(f"{failed} tool(s) failed.")
        return 1

    print("All seven tools are in Dograh.")
    print()
    print("Two things left, both in the workflow editor:")
    print("  1. Attach each tool to the node that needs it. Creating a tool does")
    print("     not enable it, and an unattached tool fails silently.")
    print("  2. Add a webhook node with this configuration:")
    print()
    print(json.dumps(webhook_hint(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
