"""Push the agent prompt into the Dograh workflow, and publish it.

Two failures this exists to prevent, both of which have already happened once:

  * the prompt field ending up with a *document about* the prompt in it, rather
    than the prompt. Pasting by hand invites that; this pushes one file whose
    entire contents are the prompt.
  * the draft never being published. An API-triggered call runs the *published*
    version, so an unpublished edit is invisible to every real call while
    looking perfect in the editor's test chat.

    python scripts/apply_dograh_prompt.py             # show the diff
    python scripts/apply_dograh_prompt.py --apply     # write the draft
    python scripts/apply_dograh_prompt.py --apply --publish

Publishing is deliberately a separate flag: it is what real calls execute.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import BACKEND_ROOT, settings  # noqa: E402

OK, BAD, SKIP = "  OK  ", " FAIL ", " SKIP "

PROMPT_PATH = BACKEND_ROOT / "config" / "dograh_prompt.txt"

# The node that carries the conversation. Dograh names the first one this in a
# generated agent; a workflow with several would need the name passed in.
PROMPT_NODE_TYPES = ("startCall", "agentNode")


def line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f" - {detail}" if detail else ""))


def _base() -> str:
    return settings.dograh_api_base.rstrip("/")


async def _workflow_id(client: httpx.AsyncClient) -> int | None:
    """Dograh keys workflows by an internal id; .env holds the agent UUID."""
    response = await client.get(f"{_base()}/api/v1/workflow/fetch")
    response.raise_for_status()
    payload = response.json()
    rows = payload if isinstance(payload, list) else payload.get("items", [])
    for row in rows:
        for field in ("workflow_uuid", "uuid", "agent_uuid"):
            if str(row.get(field) or "") == settings.dograh_workflow_uuid:
                return row.get("id") or row.get("workflow_id")
    return None


async def main() -> int:
    do_apply = "--apply" in sys.argv
    do_publish = "--publish" in sys.argv

    if not settings.dograh_configured:
        line(BAD, "Dograh configuration", "incomplete - see check_dograh.py")
        return 1
    if not PROMPT_PATH.exists():
        line(BAD, "prompt file", f"{PROMPT_PATH} is missing")
        return 1

    prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    print(f"Prompt file : {PROMPT_PATH.name} ({len(prompt)} chars)")
    print(f"Dograh      : {_base()}")
    print()

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={
            "X-API-Key": settings.dograh_api_key,
            "Content-Type": "application/json",
        },
    ) as client:
        workflow_id = await _workflow_id(client)
        if workflow_id is None:
            line(BAD, "workflow", f"{settings.dograh_workflow_uuid} not found")
            return 1

        response = await client.get(f"{_base()}/api/v1/workflow/fetch/{workflow_id}")
        response.raise_for_status()
        workflow = response.json()

        definition = (
            workflow.get("workflow_definition")
            or workflow.get("definition")
            or workflow.get("workflow_json")
        )
        if not isinstance(definition, dict):
            line(BAD, "workflow definition", f"unexpected shape: {type(definition).__name__}")
            return 1

        nodes = definition.get("nodes") or []
        targets = [n for n in nodes if n.get("type") in PROMPT_NODE_TYPES]
        if not targets:
            line(BAD, "conversation node", f"no {' or '.join(PROMPT_NODE_TYPES)} node")
            return 1

        print(f"workflow {workflow_id} ({workflow.get('name')}) - {len(nodes)} nodes")
        for node in targets:
            current = (node.get("data") or {}).get("prompt") or ""
            same = current.strip() == prompt
            first = current.strip().splitlines()[0][:56] if current.strip() else "(empty)"
            print(f"  {node.get('type')} '{(node.get('data') or {}).get('name', node.get('id'))}'")
            print(f"      now  : {len(current)} chars | {first!r}")
            print(f"      after: {len(prompt)} chars | {prompt.splitlines()[0][:56]!r}")
            if same:
                print("      already matches")
        print()

        if not do_apply:
            print("Dry run. Re-run with --apply to write the draft, and")
            print("--apply --publish to make it what real calls execute.")
            return 0

        for node in targets:
            node.setdefault("data", {})["prompt"] = prompt

        response = await client.put(
            f"{_base()}/api/v1/workflow/{workflow_id}",
            json={"workflow_definition": definition},
        )
        if response.status_code >= 400:
            line(BAD, "save draft", f"{response.status_code}: {response.text[:300]}")
            return 1
        line(OK, "draft saved", f"{len(targets)} node(s) updated")

        if not do_publish:
            print()
            print("Draft only. An API-triggered call still runs the PUBLISHED")
            print("version - re-run with --publish when you are ready.")
            return 0

        response = await client.post(f"{_base()}/api/v1/workflow/{workflow_id}/publish")
        if response.status_code >= 400:
            line(BAD, "publish", f"{response.status_code}: {response.text[:300]}")
            return 1
        line(OK, "published", "real calls now run this version")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
