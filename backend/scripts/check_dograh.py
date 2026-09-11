"""Verify the Dograh setup before handing it a real lead.

The failure mode this exists to prevent: the call connects, the lead says
"hello", and the agent either says nothing or cannot look anything up - because
the API key was archived, or the workflow's HTTP tools point at a hostname that
stopped resolving an hour ago. By then you have called a real person.

Checks, in the order a call exercises them:
  1. the API key is accepted
  2. the workflow UUID resolves to an agent
  3. a telephony configuration exists (this is where VoBiz lives)
  4. PUBLIC_BASE_URL resolves from outside, if it is set
  5. our tool endpoint refuses an unauthenticated call, and accepts a signed one
  6. optionally place a real call:  scripts/check_dograh.py +91XXXXXXXXXX

Azure Speech and VoBiz are configured inside Dograh, not here, so there is
nothing on this side to check for them - only that Dograh has a telephony
configuration at all.

Run:  .venv/Scripts/python scripts/check_dograh.py [number-to-dial]
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.dograh import client as dograh  # noqa: E402

OK, BAD, SKIP = "  OK  ", " FAIL ", " SKIP "

PROBE_CALL_ID = "CL-preflight"


def line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f" - {detail}" if detail else ""))


def _base() -> str:
    return settings.dograh_api_base.rstrip("/")


def _headers() -> dict[str, str]:
    return {"X-API-Key": settings.dograh_api_key}


async def check_api_key() -> bool:
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                f"{_base()}/api/v1/workflow/fetch", headers=_headers()
            )
    except Exception as exc:
        line(BAD, "Dograh API key", str(exc)[:300])
        return False

    if response.status_code == 401:
        line(BAD, "Dograh API key", "401 - the key is wrong, or has been archived")
        return False
    if response.status_code >= 400:
        line(BAD, "Dograh API key", f"{response.status_code}: {response.text[:200]}")
        return False

    line(OK, "Dograh API key", "accepted")
    return True


UUID_FIELDS = ("workflow_uuid", "uuid", "agent_uuid", "id")


async def check_workflow() -> bool:
    """A wrong UUID here is a 404 at dial time, on a real lead.

    Listed rather than fetched by path: Dograh keys workflows by an internal id
    and exposes a separate agent UUID, and matching against the list is the one
    way to be sure the value in .env is the one the trigger endpoint wants.
    """
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                f"{_base()}/api/v1/workflow/fetch", headers=_headers()
            )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        line(BAD, "workflow list", str(exc)[:300])
        return False

    rows = payload if isinstance(payload, list) else payload.get("items", [])
    wanted = settings.dograh_workflow_uuid

    for row in rows:
        for field in UUID_FIELDS:
            if str(row.get(field) or "") == wanted:
                name = str(row.get("name") or row.get("workflow_name") or "")[:60]
                line(OK, f"workflow {wanted}", name or "resolves")
                return True

    known = []
    for row in rows[:8]:
        uid = next((str(row[f]) for f in UUID_FIELDS if row.get(f)), "?")
        known.append(f"{row.get('name', '?')} = {uid}")
    line(BAD, f"workflow {wanted}", "not in this organization's workflows")
    if known:
        print("        Workflows this key can see:")
        for k in known:
            print(f"          {k}")
        print("        Use the agent's UUID, not an API Trigger node's.")
    return False


async def check_telephony() -> bool:
    """Where VoBiz lives.

    Dograh already knows whether a configuration can actually place a call, so
    this reads its own verdict - `is_ready_for_outbound` and
    `outbound_blocked_reason` - rather than just counting rows. A configuration
    that exists but is inactive, or has no numbers on it, fails at dial time
    with a real lead on the other end.
    """
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                f"{_base()}/api/v1/organizations/telephony-configs",
                headers=_headers(),
            )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        line(SKIP, "telephony configuration", f"could not list: {str(exc)[:200]}")
        return True

    # Dograh wraps this one; the others in this API are bare lists.
    if isinstance(payload, dict):
        rows = payload.get("configurations") or payload.get("items") or []
    else:
        rows = payload

    if not rows:
        line(BAD, "telephony configuration",
             "Dograh has none. Add VoBiz in Settings -> Telephony before dialling.")
        return False

    ready = [r for r in rows if r.get("is_ready_for_outbound")]
    if not ready:
        line(BAD, "telephony configuration", f"{len(rows)} configured, none ready for outbound")
        for r in rows:
            reason = r.get("outbound_blocked_reason") or (
                "marked inactive" if r.get("inactive") else
                "no phone numbers attached" if not r.get("phone_number_count") else
                "not ready"
            )
            print(f"        {r.get('name', '?')} ({r.get('provider', '?')}): {reason}")
        return False

    chosen = next((r for r in ready if r.get("is_default_outbound")), ready[0])
    line(
        OK,
        f"telephony '{chosen.get('name', '?')}'",
        f"{chosen.get('provider')}, id={chosen.get('id')}, "
        f"{chosen.get('phone_number_count', 0)} number(s), ready",
    )

    if chosen.get("provider") != "vobiz":
        print(f"        Note: outbound will use {chosen.get('provider')}, not VoBiz.")
    if settings.dograh_telephony_configuration_id is None and len(ready) > 1:
        print(f"        {len(ready)} configurations are ready. Pin one with "
              f"DOGRAH_TELEPHONY_CONFIGURATION_ID to remove the ambiguity.")
    return True


async def check_llm_deployment() -> bool:
    """The LLM Dograh will actually call, proven against the Azure resource.

    This has silently broken calls twice. Dograh's Azure form offers exactly
    one model, `gpt-4.1-mini`, and saves it whenever the form is touched - but
    on Azure the field must be a *deployment* name, and no deployment here is
    called that. The symptom is a call that greets, hears the lead, and then
    says nothing, because every LLM turn 404s.
    """
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            cfg = (await client.get(
                f"{_base()}/api/v1/organizations/model-configurations/v2",
                headers=_headers(),
            )).json()
        llm = cfg["effective_configuration"]["llm"]
    except Exception as exc:
        line(SKIP, "LLM deployment", f"could not read model config: {str(exc)[:120]}")
        return True

    provider, model = llm.get("provider"), llm.get("model")
    if provider != "azure":
        line(OK, "LLM", f"{provider} / {model} (not Azure; not checked here)")
        return True

    endpoint = settings.azure_openai_endpoint.rstrip("/")
    url = (f"{endpoint}/openai/deployments/{model}/chat/completions"
           f"?api-version={settings.azure_openai_api_version}")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                url,
                headers={"api-key": settings.azure_openai_api_key},
                json={"messages": [{"role": "user", "content": "ok"}], "max_tokens": 1},
            )
    except Exception as exc:
        line(BAD, f"LLM deployment '{model}'", str(exc)[:120])
        return False

    if r.status_code == 200:
        line(OK, f"LLM deployment '{model}'", "answers")
        return True

    line(BAD, f"LLM deployment '{model}'", f"Azure returned {r.status_code}")
    print("        Dograh's LLM model must be an Azure DEPLOYMENT name. Fix with:")
    print("          docker compose run --rm apply-models --apply")
    print("        and avoid re-saving the Model Configuration form in the UI -")
    print("        its dropdown only knows 'gpt-4.1-mini' and will revert this.")
    return False


LOCAL_HOSTS = ("localhost", "127.0.0.1", "host.docker.internal", "0.0.0.0", "::1")


def _is_local(url: str) -> bool:
    return any(h in url for h in LOCAL_HOSTS)


async def check_dograh_can_reach_us() -> bool:
    """The one failure this whole script exists to prevent.

    `check_public_url` below proves *this container* can reach PUBLIC_BASE_URL,
    which proves nothing about Dograh when Dograh is somewhere else. A hosted
    Dograh cannot resolve host.docker.internal or localhost - every tool call
    would fail mid-conversation while the agent keeps talking.
    """
    api_is_remote = not _is_local(settings.dograh_api_base)
    we_are_local = _is_local(settings.public_base_url)

    if api_is_remote and we_are_local:
        line(
            BAD,
            "Dograh can reach PUBLIC_BASE_URL",
            f"{settings.dograh_api_base} cannot resolve {settings.public_base_url}",
        )
        print("        Dograh is hosted, so PUBLIC_BASE_URL must be publicly")
        print("        reachable. Start a tunnel and set it to the tunnel URL:")
        print("          cloudflared tunnel --url http://localhost:8000")
        return False

    if api_is_remote:
        line(OK, "Dograh can reach PUBLIC_BASE_URL", "both are public")
    else:
        line(OK, "Dograh can reach PUBLIC_BASE_URL", "both are on this machine")
    return True


async def check_public_url() -> bool:
    """Dograh's HTTP tools and its webhook both have to reach us."""
    if not settings.public_base_url:
        line(SKIP, "PUBLIC_BASE_URL", "not set - fine if Dograh can reach this host directly")
        return True

    url = f"{settings.public_base_url.rstrip('/')}/api/health"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url)
        response.raise_for_status()
        health = response.json()
    except Exception as exc:
        line(BAD, f"PUBLIC_BASE_URL {settings.public_base_url}", str(exc)[:300])
        print("        Dograh's tools POST to this origin. If it is a tunnel, it "
              "has probably restarted and changed hostname.")
        return False

    line(
        OK,
        f"PUBLIC_BASE_URL {settings.public_base_url}",
        f"transport={health.get('transport')} orchestrator={health.get('orchestrator')}",
    )
    return True


async def check_tool_endpoint() -> bool:
    """Our own side: the tool endpoint must refuse strangers and admit Dograh."""
    base = (settings.public_base_url or "http://localhost:8000").rstrip("/")
    url = f"{base}/api/dograh/tools/capture_field"
    body = {"broker_call_id": PROBE_CALL_ID, "field": "budget", "value": "50000"}

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            unsigned = await client.post(url, json=body)
            signed = await client.post(
                url, json=body, headers={"X-Dograh-Secret": settings.dograh_shared_secret}
            )
    except Exception as exc:
        line(BAD, "tool endpoint", f"{url} unreachable: {str(exc)[:200]}")
        return False

    if unsigned.status_code != 403:
        line(
            BAD,
            "unauthenticated tool call is refused",
            f"got {unsigned.status_code} - anyone who guesses a call_id could "
            "book a viewing",
        )
        return False
    line(OK, "unauthenticated tool call is refused", "403")

    # 404 is the healthy answer here: the secret was accepted and the probe
    # call_id simply has no row. A 403 would mean the secret does not match.
    if signed.status_code == 403:
        line(BAD, "signed tool call", "403 - DOGRAH_SHARED_SECRET does not match")
        return False
    line(OK, "signed tool call", f"accepted (HTTP {signed.status_code} for a probe call_id)")
    return True


async def place_test_call(number: str) -> bool:
    print()
    print(f"Handing a call for {number} to Dograh ...")
    try:
        run_id = await dograh.place_call(
            to=number,
            call_id=PROBE_CALL_ID,
            context={"first_name": "Preflight", "lead_type": "renter"},
        )
    except Exception as exc:
        line(BAD, "outbound call", str(exc)[:400])
        return False

    line(OK, "outbound call", f"queued, workflow_run_id={run_id}")
    print("        A 2xx means the run was created, not that anyone answered.")
    print(f"        Note: call_id={PROBE_CALL_ID} has no database row, so the "
          "agent's tools will 404. This proves the carrier path only.")
    return True


async def main() -> int:
    print(f"Dograh API     : {settings.dograh_api_base}")
    print(f"Workflow UUID  : {settings.dograh_workflow_uuid or '(not set)'}")
    print(f"Public base URL: {settings.public_base_url or '(not set)'}")
    print(f"Transport      : {settings.transport}")
    print()

    if not settings.dograh_configured:
        line(
            BAD,
            "Dograh configuration",
            "DOGRAH_API_BASE, DOGRAH_API_KEY, DOGRAH_WORKFLOW_UUID and "
            "DOGRAH_SHARED_SECRET are all required",
        )
        return 1

    results = [
        await check_api_key(),
        await check_workflow(),
        await check_telephony(),
        await check_llm_deployment(),
        await check_dograh_can_reach_us(),
        await check_public_url(),
        await check_tool_endpoint(),
    ]

    number = sys.argv[1] if len(sys.argv) > 1 else ""
    if number:
        if all(results):
            results.append(await place_test_call(number))
        else:
            print()
            line(SKIP, "outbound call", "earlier checks failed; not dialling a real number")

    failed = results.count(False)
    print()
    if failed:
        print(f"{failed} check(s) failed. Fix these before calling a lead.")
    else:
        print("Dograh is ready. Set CALL_TRANSPORT=dograh and 'Call now' places "
              "a real call.")
    await dograh.aclose()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
