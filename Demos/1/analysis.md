# Demo 1 — Analysis, outbound and memory

**Call** `CL-0018` · **Lead** Aditya Banerjee · **Duration** 3:01 · **Status after call** `Qualified`

## 1. Call metrics (deterministic, from timestamps)

| Metric | Value |
|---|---|
| Turns | 16 |
| Agent talk ratio | 74% |
| Average agent latency | 6822 ms |
| Dead-air events (>3 s) | 8 |

## 2. Conversion track (LLM-2a)

| Field | Value |
|---|---|
| Completeness | 100% |
| Fields captured | monthly_rent_min, monthly_rent_max, preferred_areas, bhk_config |
| Fields missing | — |
| Next step secured | no |
| Next step | — |
| Lead temperature | warm |
| Conversion score | 0.85 |
| Proposed lead status | Qualified |

**Objection handling** — score 3/5

> The lead did not raise any objections during the call.

## 3. Safety track (LLM-2b)

**Verdict: `pass`** — 0 violation(s), 0 unverified claim(s), 0 pressure flag(s)


**Escalation judgement**

- Should have escalated: no
- Did escalate: no

**Gate result:** lead status → `Qualified`

## 4. Memory extracted (LLM-2c)

The memory compactor *consolidates* rather than appends: each run rewrites the lead's memory from the whole history, and the entries carry the id of the run that last wrote them. This call's entries were superseded by a later call, so its own version is no longer stored. The **current consolidated memory** the agent will start the next call from (v11) is:

- **preference** — Aditya Banerjee is looking for a 2 BHK rental or a villa in Gurugram, preferably in Sector 54, with a budget of ₹50,000 to ₹75,000.  _(from CL-0019)_
- **preference** — Aditya is open to any furnishing status for the property.  _(from CL-0019)_
- **commitment** — Aditya has requested to be notified when suitable properties become available.  _(from CL-0019)_

**Memory block as injected into the next call's prompt:**

```
MEMORY (from 11 earlier calls)
- Aditya Banerjee is looking for a 2 BHK rental or a villa in Gurugram, preferably in Sector 54, with a budget of ₹50,000 to ₹75,000.
- Aditya is open to any furnishing status for the property.
- Aditya has requested to be notified when suitable properties become available.
```

## 5. Outbound follow-up (LLM-3, drafted — not sent)

**Message** `MS-0010` · status `draft`

**WhatsApp**

```
Hello Aditya, I will check availability of 2BHKs, villas, and penthouses near Sector 54 within your budget and share the options with you shortly. Please let me know if you have any other preferences.
```

**Email** — subject: *Follow-up on Your Property Search Near Sector 54*

```
Dear Aditya,

Thank you for sharing your preferences during our call. I will look for 2BHK apartments, villas, or penthouses near Sector 54 within your updated budget of Rs 50,000 to Rs 1,00,000 per month. Currently, I have a 2BHK semi-furnished apartment in Palm Grove Heights, Sector 82, which I can share details about if you are interested.

I will confirm availability of other suitable properties near Sector 54 and get back to you soon.

Please feel free to share any additional requirements.

Best regards,
Asha, on behalf of the team
```
