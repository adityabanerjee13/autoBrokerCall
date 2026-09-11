"""The architectural invariants from the handoff, as tests.

These are the rules a future change is most likely to break by accident and
least likely to notice: memory leaking into an API, a second model client, a
tool that can take money, a blended score. Each one is a grep in the spec's
definition of done; here it fails a build instead.
"""
import re
from pathlib import Path

from app.agent.tools import TOOL_SCHEMAS
from app.config import BACKEND_ROOT

APP = BACKEND_ROOT / "app"
API = APP / "api"
SCRIPTS = BACKEND_ROOT / "scripts"


def sources(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def test_no_api_route_touches_lead_memory():
    offenders = [p for p in sources(API) if "lead_memory" in p.read_text(encoding="utf-8")]
    assert not offenders, (
        "lead_memory is agent-private and must not be reachable over HTTP: "
        f"{[str(p.relative_to(BACKEND_ROOT)) for p in offenders]}"
    )


def test_only_azure_client_constructs_a_model_client():
    pattern = re.compile(r"\bAsyncAzureOpenAI\b|\bAzureOpenAI\b")
    offenders = [
        p
        for p in sources(APP)
        if pattern.search(p.read_text(encoding="utf-8"))
        and p.name != "azure_client.py"
    ]
    assert not offenders, (
        "every model call goes through llm/azure_client.py: "
        f"{[str(p.relative_to(BACKEND_ROOT)) for p in offenders]}"
    )


def test_the_agent_has_no_tool_for_money_advice_or_messaging():
    names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    assert names == {
        "capture_field",
        "search_properties",
        "present_property",
        "book_appointment",
        "note_memory",
        "escalate_to_human",
        "end_call",
    }
    forbidden = re.compile(r"pay|token|deposit|transfer|loan|emi|tax|send|whatsapp|email|sms")
    assert not [n for n in names if forbidden.search(n)]


def test_escalate_to_human_is_always_available_to_every_lead_type():
    from app.agent.tools import TOOL_LEAD_TYPES

    assert TOOL_LEAD_TYPES["escalate_to_human"] == {"renter", "lender"}


def test_nothing_computes_a_combined_conversion_and_safety_score():
    """The two tracks are reported side by side and never blended."""
    from app.models import AnalysisRow, CallAnalysis

    fields = set(AnalysisRow.model_fields) | set(CallAnalysis.model_fields)
    blended = [f for f in fields if re.search(r"overall|combined|total|blend", f)]
    assert not blended, f"combined score fields found: {blended}"


def test_twilio_is_gone_and_cannot_come_back():
    """There is no Twilio in this codebase, and no Pipecat that would need one.

    Removing a provider is only removing it if it cannot creep back one import
    at a time, so this greps every source file rather than trusting that the
    modules stay deleted. `twilio_call_sid` on a document counts: a field named
    after a vendor outlives the vendor.
    """
    pattern = re.compile(r"twilio|pipecat|twiml|programmable ?voice", re.IGNORECASE)
    offenders = [
        p
        for p in sources(APP) + sources(SCRIPTS)
        if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "Twilio was removed; the carrier is VoBiz: "
        f"{[str(p.relative_to(BACKEND_ROOT)) for p in offenders]}"
    )


def test_no_carrier_or_speech_credential_lives_in_this_repo():
    """Dograh owns the call, and therefore owns the credentials for it.

    VoBiz and Azure Speech are configured inside Dograh - the carrier provider
    and the STT/TTS services are its concern now. A carrier auth token or a
    speech key appearing here means the seam has leaked and two systems are
    each half-holding the call.
    """
    pattern = re.compile(
        r"vobiz_auth_token|vobiz_auth_id|api\.vobiz\.ai"
        r"|azure_speech_key|tts\.speech\.microsoft\.com"
        r"|cognitiveservices\.speech",
        re.IGNORECASE,
    )
    offenders = [
        p for p in sources(APP) if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "VoBiz and Azure Speech are configured in Dograh, not here: "
        f"{[str(p.relative_to(BACKEND_ROOT)) for p in offenders]}"
    )


def test_only_the_dograh_client_holds_an_orchestrator_credential():
    """One module talks to Dograh, as one module talks to the model.

    `dograh/client.py` is the only place that holds an API key or knows the
    shape of Dograh's API. `api/dograh.py` is the only surface Dograh can
    reach back through, and it authenticates rather than trusting the caller.
    """
    allowed = {"config.py", "dograh/client.py", "api/dograh.py"}
    pattern = re.compile(r"dograh_api_key|dograh_shared_secret|X-API-Key")
    offenders = [
        p
        for p in sources(APP)
        if pattern.search(p.read_text(encoding="utf-8"))
        and p.relative_to(APP).as_posix() not in allowed
    ]
    assert not offenders, (
        "Dograh credentials belong to dograh/client.py alone: "
        f"{[str(p.relative_to(BACKEND_ROOT)) for p in offenders]}"
    )


def test_every_dograh_route_authenticates():
    """These routes are on the public internet and both write to the database.

    An unauthenticated POST to /api/dograh/tools/book_appointment would book a
    viewing on a real lead, and one to /api/dograh/webhook would close out and
    grade a live call. Every route body must reach `_authenticate`.
    """
    import ast

    tree = ast.parse((API / "dograh.py").read_text(encoding="utf-8"))

    unchecked = []
    for node in tree.body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        decorators = " ".join(ast.dump(d) for d in node.decorator_list)
        if "router" not in decorators:
            continue
        if "_authenticate" not in ast.dump(node):
            unchecked.append(node.name)

    assert not unchecked, f"unauthenticated dograh routes: {unchecked}"


def test_the_guardrail_still_runs_on_this_side_of_the_seam():
    """Moving the conversation to an orchestrator did not move the rules.

    Dograh proposes a tool call; `agent/turn.py::run_tool` decides whether it
    is allowed. If the tool endpoint ever called `tools.execute` directly it
    would be handing the agent unguarded database access.
    """
    source = (API / "dograh.py").read_text(encoding="utf-8")
    assert "run_tool" in source, "the tool endpoint must go through run_tool"
    assert "import execute" not in source and "tools.execute" not in source, (
        "the tool endpoint must not bypass the guardrail by executing directly"
    )


def test_the_only_transports_are_the_orchestrator_and_the_script():
    """Two values. Nobody answers a call in a browser tab any more."""
    from app.config import Settings

    assert Settings(call_transport="mock").transport == "mock"
    # Anything unrecognised - including whatever a stale .env still carries -
    # resolves to the script rather than failing at the orchestrator.
    for stale in ("nonsense", "twilio", "browser", "vobiz"):
        assert Settings(call_transport=stale).transport == "mock", stale


def test_asking_for_dograh_without_credentials_runs_the_script_not_a_call():
    """A half-configured orchestrator must degrade, not dial into the void."""
    from app.config import Settings

    half = Settings(
        call_transport="dograh",
        dograh_api_key="dg_test",
        dograh_workflow_uuid="wf-1",
        dograh_shared_secret="",     # nothing to authenticate tool calls with
    )
    assert half.transport == "mock"

    whole = half.model_copy(update={"dograh_shared_secret": "s3cret"})
    assert whole.transport == "dograh"


def test_nothing_answers_a_call_in_a_browser():
    """The handset transport is gone, and must not drift back in.

    It came back once already as a half-built feature: a fully wired backend
    route with a missing frontend, which failed the build rather than the
    tests. This greps for the route rather than trusting the file stays deleted.
    """
    offenders = [
        p
        for p in sources(APP)
        if "api/handset" in p.read_text(encoding="utf-8").replace("\\", "/")
        or "/api/voice" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        "the lead answers a phone, not a browser tab: "
        f"{[str(p.relative_to(BACKEND_ROOT)) for p in offenders]}"
    )


def test_the_handoff_line_is_a_constant_not_a_prompt_to_the_model():
    """The only place the handoff text is produced is escalation.handoff_message."""
    from app.agent import escalation

    line = escalation.handoff_message()
    agent_path = APP / "agent"
    producers = [
        p
        for p in sources(agent_path)
        if line[:40] in p.read_text(encoding="utf-8")
    ]
    assert not producers, (
        "the handoff line must come from policy.yaml at runtime, never be "
        f"hard-coded in the agent path: {[p.name for p in producers]}"
    )
