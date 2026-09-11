# brokerAgent

A voice agent that calls rental leads in Gurugram, qualifies them, books
viewings, and hands off to a human when it must. Every call is graded on two
independent tracks, its durable facts are compressed into memory for the next
call, and a follow-up is drafted for a broker to send with one click. Three
dashboards — broker, home-owner, manager — behind one toggle.

**Stack.** [Dograh](https://docs.dograh.com) orchestrates the call over a VoBiz
line with Azure Speech (`en-IN`) on both ends. Azure OpenAI runs the agent and
the post-call pipeline. FastAPI + MongoDB on the backend, React on the front.

---

## How to run

Everything runs in Docker. No Python, Node or Mongo needed on the host.

```bash
cp backend/.env.example backend/.env
docker compose up -d --build
docker compose run --rm seed
```

Open **http://localhost:5173**. With `CALL_TRANSPORT=mock` (the default) the
lead's side is replayed from `backend/seed/scripts`, so no Dograh account is
needed — everything on the agent's side is real.

| Command | What it does |
|---|---|
| `docker compose run --rm test` | 83-test suite, including the architectural invariants |
| `docker compose run --rm check-azure` | verify the three model deployments |
| `docker compose run --rm check-dograh` | verify the Dograh key, workflow, telephony and tool reachability |
| `docker compose run --rm provision-dograh --apply --attach --publish` | create the seven tools in Dograh and attach them |
| `docker compose run --rm apply-prompt --apply --publish` | push `config/dograh_prompt.txt` and publish |
| `docker compose run --rm apply-models --apply` | pin Dograh's LLM/TTS/STT to what the call needs |

**Real calls.** Fill in `DOGRAH_API_KEY`, `DOGRAH_WORKFLOW_UUID`,
`DOGRAH_SHARED_SECRET` and a public `PUBLIC_BASE_URL` (Dograh calls back into
this app; a Cloudflare tunnel works), set `CALL_TRANSPORT=dograh`, and run
`check-dograh` until all checks pass. VoBiz and Azure Speech are configured
inside Dograh, not here. **Call now** on the broker dashboard then dials.

---

## What is covered

### Voice agent (Dograh)

**Integration over HTTP.** Dograh owns the call — carrier, speech, turn-taking
— and this app owns the domain. The seam is three HTTP surfaces:

- `POST /api/v1/public/agent/workflow/{uuid}` — this app hands a call to Dograh
  with `initial_context`: the lead digest, matched properties, the memory block,
  today's date in IST, and a `broker_call_id` that threads everything back.
- `POST /api/dograh/tools/{name}` — Dograh calls back into this app for every
  tool the agent uses. **The guardrail still runs here**: Dograh proposes, this
  app decides, and a refusal returns as words the agent can recover from.
- `POST /api/dograh/webhook` — fired when the run completes; this app fetches
  the transcript and starts the post-call pipeline.

All three are authenticated with a shared secret. A tool call that fails the
check is refused, and a webhook retry for a call already graded is ignored.

**Seven tools.** `capture_field`, `search_properties`, `present_property`,
`book_appointment`, `note_memory`, `escalate_to_human`, `end_call`. There is
deliberately no tool for payments, loans, advice or messaging, and none that
can move a property back to `available` — an invariant test fails the build if
one appears. `provision-dograh` creates them in Dograh from the same schemas
the scripted runner uses, so the two cannot drift.

**The `end_call` modification.** Six tools are HTTP tools; `end_call` is not.
An HTTP tool that says "the call is over" is just an HTTP request — the line
stays open, which is exactly what happened. It is provisioned as Dograh's
*native* end-call tool instead, with `endCallReason` on, so the model's reason
becomes the call disposition and reaches this app on the webhook.

**Azure AI.** Four LLM roles. LLM-1 (the conversation) runs inside Dograh on
Azure OpenAI; LLM-2a/2b (grading), LLM-2c (memory) and LLM-3 (follow-up) run
here through `llm/azure_client.py`, the only module that constructs a client.
On Azure the model field is the *deployment name* (`gpt-4o-broker`), not the
model name — `apply-models` pins it and proves the deployment answers before
saving, because Dograh's form reverts it.

### Analysis

Two judges, run separately on the transcript, reported side by side and
**never blended** — a call that books a viewing and breaks the law would
otherwise average out to "fine". Neither is shown the other's output.

**Conversion rubric (LLM-2a)** grades commercial effectiveness only:
`fields_captured` / `fields_missing` against the required fields for the lead
type (a field counts only if stated on this call or already on file);
`next_step_secured`, true only for a specific dated commitment;
`objection_handling` scored 1–5 (3 when no objection was raised — never invent
one); `lead_temperature` hot/warm/cold; a `proposed_status`; and a
`track_score` weighted 0.4 completeness, 0.35 next step, 0.25 objections.

**Safety rubric (LLM-2b)** grades conduct only, and judges what the *agent*
said. Ten rules: `escalation_missed`, `escalation_explained`,
`handoff_altered`, `spoke_after_handoff`, `unverified_claim`,
`discrimination_entertained`, `cash_or_payment`, `out_of_scope_advice`,
`pressure`, `privacy_leak`. Each violation cites the turn and a verbatim quote.
Listing attributes quoted accurately are not claims; prose facts absent from
VERIFIED FACTS are. Verdict is `pass`, `warn` or `fail`, plus an escalation
judgement (`should_have`, `did`, `miss_type`).

**The gate is literal.** `safety.verdict == "fail"` forces the lead to
`Escalated` regardless of the conversion score. Metrics — talk ratio, latency,
dead air, turn count — are arithmetic from timestamps, never asked of a model.

### Memory compression

**What the compactor does.** LLM-2c is the *only* writer of `lead_memory`. It
runs after a call, never during one, and rewrites the lead's whole memory block
from the previous block plus what the latest call established — durable facts
only: preferences, constraints, rejection reasons, who else decides, how they
like to be spoken to, commitments, sensitivities. Duplicates merge; anything
the latest call contradicts is dropped. It never records religion, caste,
community, marital status, food habits, region, payment details, or anything
said during an escalation. Hard cap 1200 tokens; over that it asks for a merge
rather than truncating, and on repeated failure keeps the previous version.

**How it helps the next call.** The block is injected verbatim into the agent's
prompt as "what earlier calls established", so the agent opens as a follow-up
rather than re-qualifying from scratch, doesn't re-ask what is known, and
avoids what the person has already rejected. The manager drill-down shows what
each call wrote, because a memory entry is what steers the next call — an
unreviewable memory is an unreviewable agent.

**What could be added at this stage.** Per-fact confidence and provenance
(which turn a fact came from), so a contradicted fact decays instead of being
dropped outright; a staleness horizon, so a budget stated six months ago is
re-confirmed rather than trusted; a diff between versions surfaced to the
manager; and a signal for facts the agent *used* on the next call versus facts
that sat unused, which would tell you what is worth remembering at all.

### Outbound

**Purpose.** LLM-3 drafts the follow-up — a WhatsApp body and an email — from
the graded call, in Gurugram local time, at status `draft`. It has no send
capability and never will. `outbound/send.py` is the only code path that sends,
it is reached only by a person clicking **Send follow-up** after reading the
draft, and its status filter makes a double-click send exactly once. Drafting
and sending are separated so that no model can put a message in front of a
customer on its own.

---

## Layout

```
backend/app/
  agent/      context, tools, guardrail, escalation, turn, mock_runner, finalize
  analysis/   metrics (deterministic), analyzer (LLM-2a/2b), rubrics/
  memory/     reader (prompt-time), compactor (LLM-2c, the only writer)
  outbound/   composer (LLM-3, drafts only), send (the button)
  dograh/     client — the only module holding a Dograh credential
  api/        calls, dograh, broker, client, manager, messages
  llm/        azure_client — the only model client
backend/scripts/   check_dograh, provision_dograh, apply_dograh_prompt, apply_dograh_models
frontend/src/      dashboards/ Broker, Client, Manager · components/CallDrawer (the audit view)
```
