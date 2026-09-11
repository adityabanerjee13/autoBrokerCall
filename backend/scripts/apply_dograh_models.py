"""Pin Dograh's model configuration to what this app actually needs.

The one setting that has silently broken calls twice: Dograh's LLM `model`
field. On Azure that field must be a *deployment name*, and the UI keeps
landing on `gpt-4.1-mini` - the model's name, which no deployment here has.
The result is a call that greets, hears the lead, and then says nothing,
because every LLM turn is a 404.

This sets the three services explicitly and, before saving, proves the LLM
deployment answers - so a wrong value is refused here rather than discovered on
a live lead.

    python scripts/apply_dograh_models.py            # show current vs wanted
    python scripts/apply_dograh_models.py --apply    # write it

Secrets are safe to round-trip: Dograh's save endpoint merges masked API keys
back to the stored values (merge_ai_model_configuration_v2_secrets).
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402

OK, BAD = "  OK  ", " FAIL "

# What the call needs. The LLM deployment is the agent's own; the other two are
# named for Gurugram callers rather than the en-US defaults Dograh starts with.
WANTED = {
    "llm": {"provider": "azure", "model": settings.azure_deployment_agent,
            "endpoint": settings.azure_openai_endpoint},
    "tts": {"provider": "azure_speech", "voice": "en-IN-NeerjaNeural", "language": "en-IN"},
    "stt": {"provider": "azure_speech", "language": "en-IN"},
}


def line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f" - {detail}" if detail else ""))


async def deployment_answers(deployment: str) -> tuple[bool, str]:
    """Prove the deployment exists by asking it for one token."""
    endpoint = settings.azure_openai_endpoint.rstrip("/")
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={settings.azure_openai_api_version}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                url,
                headers={"api-key": settings.azure_openai_api_key},
                json={"messages": [{"role": "user", "content": "ok"}], "max_tokens": 1},
            )
    except Exception as exc:
        return False, str(exc)[:120]
    if r.status_code == 200:
        return True, "answers"
    try:
        code = r.json().get("error", {}).get("code", "")
    except ValueError:
        code = ""
    return False, f"{r.status_code} {code}".strip()


async def main() -> int:
    do_apply = "--apply" in sys.argv
    base = settings.dograh_api_base.rstrip("/")

    async with httpx.AsyncClient(
        timeout=40.0,
        headers={"X-API-Key": settings.dograh_api_key, "Content-Type": "application/json"},
    ) as client:
        cfg = (await client.get(f"{base}/api/v1/organizations/model-configurations/v2")).json()["configuration"]
        pipe = cfg["byok"]["pipeline"]

        changes = []
        for svc, want in WANTED.items():
            for field, value in want.items():
                have = pipe[svc].get(field)
                if have != value:
                    changes.append((svc, field, have, value))
                    pipe[svc][field] = value

        if not changes:
            line(OK, "model configuration", "already as wanted")
        else:
            print("changes:")
            for svc, field, have, value in changes:
                print(f"  {svc}.{field}: {have!r} -> {value!r}")
        print()

        ok, why = await deployment_answers(pipe["llm"]["model"])
        if not ok:
            line(BAD, f"LLM deployment '{pipe['llm']['model']}'", why)
            print("       Refusing to save a deployment that does not answer.")
            return 1
        line(OK, f"LLM deployment '{pipe['llm']['model']}'", why)

        if not changes:
            return 0
        if not do_apply:
            print()
            print("Dry run. Re-run with --apply to write it.")
            return 0

        r = await client.put(f"{base}/api/v1/organizations/model-configurations/v2", json=cfg)
        if r.status_code >= 400:
            line(BAD, "save", f"{r.status_code}: {r.text[:300]}")
            return 1

        eff = r.json()["effective_configuration"]
        line(OK, "saved", f"llm={eff['llm']['model']} tts={eff['tts']['voice']} stt={eff['stt']['language']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
