# Demo 2 — Analysis, outbound and memory

**Call** `CL-0019` · **Lead** Aditya Banerjee · **Duration** 3:33 · **Status after call** `Qualified`

## 1. Call metrics (deterministic, from timestamps)

| Metric | Value |
|---|---|
| Turns | 18 |
| Agent talk ratio | 80% |
| Average agent latency | 9325 ms |
| Dead-air events (>3 s) | 13 |

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

**Objection handling** — score 5/5

> The agent effectively clarified the lead's requirements when there was confusion about the furnishing preference. They confirmed the updated preferences and adjusted the search accordingly.

## 3. Safety track (LLM-2b)

**Verdict: `pass`** — 0 violation(s), 0 unverified claim(s), 0 pressure flag(s)


**Escalation judgement**

- Should have escalated: no
- Did escalate: no

**Gate result:** lead status → `Qualified`

## 4. Memory extracted (LLM-2c)

**Written by the compactor** — lead memory is at **v11**, and these entries are attributed to this call:

- **preference** — Aditya Banerjee is looking for a 2 BHK rental or a villa in Gurugram, preferably in Sector 54, with a budget of ₹50,000 to ₹75,000.
- **preference** — Aditya is open to any furnishing status for the property.
- **commitment** — Aditya has requested to be notified when suitable properties become available.

**Memory block as injected into the next call's prompt:**

```
MEMORY (from 11 earlier calls)
- Aditya Banerjee is looking for a 2 BHK rental or a villa in Gurugram, preferably in Sector 54, with a budget of ₹50,000 to ₹75,000.
- Aditya is open to any furnishing status for the property.
- Aditya has requested to be notified when suitable properties become available.
```

## 5. Outbound follow-up (LLM-3, drafted — not sent)

**Message** `MS-0011` · status `sent`

**WhatsApp**

```
Hello Aditya, thank you for your time today. I will keep searching for 2BHK properties in or near Sector 54 within your budget of Rs 50,000 to Rs 75,000 and notify you when I find suitable options. Please feel free to reach out if you have any questions.
```

**Email** — subject: *Follow-up on your 2BHK rental enquiry in Sector 54*

```
Dear Aditya,

Thank you for speaking with me today. As discussed, I am currently searching for 2BHK properties in or near Sector 54 within your budget of Rs 50,000 to Rs 75,000, with any furnishing status. At present, there are no available options matching your criteria, but I will notify you as soon as I find suitable properties.

Please feel free to contact me if you have any further preferences or questions.

Best regards,
Asha, on behalf of the team
```
