# brokerAgent

A voice agent that calls rental leads in Gurugram, escalates to a human when it
must, grades every call on two independent axes, and lets a broker send the
follow-up with one click. Three dashboards — broker, home owner, manager — behind
one toggle.

## Run the demo

Everything runs in Docker. No Python, Node or Mongo needed on the host.

```bash
cp backend/.env.example backend/.env
```

```bash
docker compose up -d --build
```

```bash
docker compose run --rm seed
```

Open **http://localhost:5173**. `CALL_TRANSPORT=mock` is the default, so no
carrier account and no Azure Speech resource are required - the lead's side is
replayed from `seed/scripts`, and everything on the agent's side is real.

| Command | What it does |
|---|---|
| `docker compose up -d --build` | mongo + api + web, with healthchecks and ordering |
| `docker compose run --rm seed` | populate the five collections (safe to re-run) |
| `docker compose run --rm test` | the 30-test suite, inside the container |
| `docker compose run --rm check-azure` | verify the three model deployments |
| `docker compose run --rm check-voice` | verify Azure Speech, and write a sample to listen to |
| `docker compose run --rm check-vobiz +91XXXXXXXXXX` | verify the carrier, then optionally dial |
| `docker compose logs -f api` | backend logs |
| `docker compose down` | stop (add `-v` to drop the database too) |

Three services: `mongo:7`, `brokeragent-api` (437MB) and `brokeragent-web`
(74MB — nginx serving the built SPA).

**The frontend is same-origin with the API.** nginx proxies `/api` to the api
container, so `VITE_API_BASE` is empty in the image, there is no CORS in the
container path, and the image is not tied to a particular backend hostname. That
proxy also carries the websocket upgrade, which is what the VoBiz media stream
needs. Port 8000 is published as well, but only for poking the API directly.

### Running it without Docker

Still supported, and what you want if you are editing the frontend and need HMR:

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

The dev server needs `frontend/.env` to contain
`VITE_API_BASE=http://localhost:8000`, since it has no nginx in front of it.
Nothing may listen on 5173 or 8000 on the host while the containers hold those
ports — if the page shows `@vite/client` in its HTML, you are looking at the dev
server, not the container.

## Azure AI Foundry setup

Three deployments, on a resource in **swedencentral**. Verify any setup with:

```bash
cd backend && .venv/Scripts/python scripts/check_azure.py
```

It runs what the app runs — a completion, a tool call, and a strict
`json_schema` call on each of the analyzer and composer deployments — and
reports per-deployment rather than failing on the first error.

| `.env` key | Deployment | Model | SKU | TPM |
|---|---|---|---|---|
| `AZURE_DEPLOYMENT_AGENT` | `gpt-4o-broker` | gpt-4o `2024-11-20` | Standard | 30K |
| `AZURE_DEPLOYMENT_ANALYZER` | `gpt-4o-analyzer` | gpt-4o `2024-11-20` | Standard | 20K |
| `AZURE_DEPLOYMENT_COMPOSER` | `gpt-41-mini-composer` | gpt-4.1-mini `2025-04-14` | GlobalStandard | 50K |

Three things that are easy to get wrong:

- **`GlobalStandard` is not the default answer.** Quota is allocated per SKU
  *and* per region. This subscription has zero gpt-4o quota on GlobalStandard
  everywhere, and 50K on regional `Standard` in swedencentral and eastus2.
  Check with `az cognitiveservices usage list --location <region>` before
  deploying; an `InsufficientQuota` error is quota, not access.
- **`gpt-4o-mini` is retired** for new deployments (since 2026-03-31), and it
  only ever shipped one version. The model catalogue still lists it as live
  until 2027 — the catalogue and the deployment gate disagree, and the gate
  wins. `gpt-4.1-mini` replaces it here.
- **Structured output needs gpt-4o `2024-08-06` or later.** The analyzer and
  composer use `strict: true` schemas; an older gpt-4o will fail those two
  while the agent keeps working.

```bash
docker compose run --rm check-voice
```

That issues a token, confirms `AZURE_SPEECH_VOICE` actually exists in
`AZURE_SPEECH_REGION`, and writes a synthesised sample to your temp directory
so you can hear the voice rather than trust a byte count. A wrong voice name is
otherwise a 400 on every turn with a vague message.

**There is no fallback voice, by design.** A phone line has no speech engine of
its own, so an unconfigured `AZURE_SPEECH_KEY` is a call that connects to
silence. `synthesize()` raises rather than returning empty audio, and the
startup log warns when `CALL_TRANSPORT=vobiz` is set without a speech key. Run
`check-voice` before you need it, not after.

## Telephony: VoBiz

[VoBiz](https://vobiz.ai/docs) dials the lead. Two modules know it exists:
`telephony/vobiz.py` holds the credentials and the wire format, and
`api/vobiz.py` is the only surface the carrier can reach.

The carrier drives the call by calling us:

```
POST /Account/{auth_id}/Call/   ->  request_uuid          (queued, not answered)
        |
        v
  answer_url    -> we return <Stream> XML  -> wss://…/api/vobiz/media/{call_id}
  ring_url      -> logged
  machine_url   -> voicemail? <Hangup/>
  hangup_url    -> the authoritative end of the call
```

Everything between the two audio directions is Azure Speech and
`agent/session.py`:

```
caller audio -> Azure STT -> CallSession.lead_turn() -> Azure TTS -> caller
```

`agent/session.py` owns no transport, which is what lets the scripted runner
walk the same ground with nobody on the line - so a scripted call and a real
one produce the same documents and are graded the same way.

### Turning it on

Build the api image with the Speech SDK, since a dialled call has to hear:

```bash
WITH_TELEPHONY=true docker compose up -d --build
```

Fill in `AZURE_SPEECH_KEY`, the three `VOBIZ_*` settings and `PUBLIC_BASE_URL`,
set `CALL_TRANSPORT=vobiz`, then verify before dialling a real person:

```bash
docker compose run --rm check-vobiz +91XXXXXXXXXX
```

That checks the credentials, fetches `/api/health` back through
`PUBLIC_BASE_URL` from the outside, fetches the answer webhook and parses the
XML, confirms an *unsigned* webhook is refused, and synthesises a sample at the
phone line's format. Only then, and only if a number was passed, does it dial.

**All four VoBiz settings are required, and a missing one replays a script
instead.** `settings.transport` resolves `vobiz` to `mock` unless the auth id,
auth token, from-number and `PUBLIC_BASE_URL` are all present, and logs a
warning at startup saying so. Dialling a real person and then having nothing
answer is worse than not dialling.

**Point the tunnel at port 5173, not 8000.** nginx proxies `/api` including the
websocket upgrade, so the whole carrier path works through the web container.
Whenever the tunnel restarts its hostname changes, and a stale
`PUBLIC_BASE_URL` is a call that connects to silence. After changing it:
`docker compose up -d --force-recreate api`.

ngrok needs an account; Cloudflare quick tunnels do not:

```bash
cloudflared tunnel --url http://localhost:5173
```

### Things that are load-bearing on a real call

**The webhooks are signed.** They are on the public internet and they end live
calls, so every callback URL carries an HMAC over the `call_id` and every route
checks it — including the media socket, which rejects the upgrade rather than
accepting and then failing.
`tests/test_invariants.py::test_every_carrier_webhook_checks_its_signature`
parses the module and fails the build if a route stops checking.

**Nothing speaks before the stream.** The answer XML has no `<Speak>`: a
carrier greeting would be a different voice from every line after it, so the
greeting comes out of Azure through the same socket as the rest of the call.

**`keepCallAlive="true"` is not optional.** Without it the carrier runs the
next element the moment the stream is set up and hangs up before anyone has
said anything.

**The agent stops talking when the caller starts.** Playback is sent in 200ms
chunks and abandoned mid-line on barge-in, and `clearAudio` flushes what the
carrier has already buffered. An agent that talks over an interruption is worse
than one that is slow.

**A voicemail is not a lead.** VoBiz's machine detection posts to
`/api/vobiz/machine`; a detected machine gets `<Hangup/>` and the lead goes
back in the queue rather than being pitched to.

**The socket closing is not the call ending.** With `keepCallAlive` the line
stays up until someone hangs up, so the runner calls `vobiz.hangup()` in its
`finally` rather than assuming the carrier noticed.

## Layout

```
backend/app/
  agent/      context, tools, guardrail, escalation, session, mock_runner,
              vobiz_runner, finalize
  analysis/   metrics (deterministic), analyzer (LLM-2a/2b), schemas, rubrics/
  memory/     reader (prompt-time), compactor (LLM-2c, the only writer)
  outbound/   composer (LLM-3, drafts only), send (the button), whatsapp, email
  voice/      azure_speech — the only speech engine in the codebase
  telephony/  vobiz — the only carrier in the codebase
  api/        calls, vobiz, broker, client, manager, messages
  llm/        azure_client — the only model client in the codebase
backend/Dockerfile               api image; WITH_TELEPHONY=true adds the Speech SDK
backend/scripts/                 check_azure.py, check_voice.py, check_vobiz.py
frontend/Dockerfile              node build -> nginx, serves the SPA and proxies /api
docker-compose.yml               mongo + api + web, plus seed/test/check one-shots
frontend/src/
  api/        client, types (mirrors the DTOs), hooks (one per endpoint)
  components/ RoleToggle, LeadQueue, ActiveCallPanel, CompletedCalls, CallDrawer
  dashboards/ Broker, Client, Manager
```

## Known deviations from the handoff spec

- **Retry.** The spec's `send.py` filters on `status: "draft"` alone, which would
  make the "Retry" button on a `partial`/`failed` row 409 forever. The filter here
  is `{"$in": ["draft", "partial", "failed"]}` — a second click during a send
  still lands on `"sending"` and is refused, so double-click safety is unchanged.
- **Seed consistency.** The spec asks for six `Queued` renters *and* a completed
  call with `safety.verdict = "fail"`. Since the gate forces `Escalated` on a
  safety failure, that call's lead (Meera Raghavan) is seeded as `Escalated` and
  a seventh queued renter was added, so the queue still shows six.
- **`present_property` does not change `properties.status`.** Keeping it
  `available` is what lets a viewing be booked against a property that was just
  presented, and it keeps guardrail rule 4 literally `status != "available"`.
- **Offline fallbacks.** Described above; they exist so the demo runs before any
  Azure deployment is provisioned.
