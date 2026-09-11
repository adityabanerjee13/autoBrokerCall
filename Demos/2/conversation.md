# Demo 2 — Conversation

**Call** `CL-0019` · **Lead** Aditya Banerjee (renter) · **Duration** 3:33 · **Transport** dograh · **Dograh run** `695356`

Started 11 Sep 2026, 13:01:53 IST · Ended 11 Sep 2026, 13:06:01 IST

The agent is **Asha** (Azure Speech `en-IN-NeerjaNeural`, LLM `gpt-4o-broker` on Azure OpenAI), orchestrated by Dograh over a VoBiz line. Every tool call below is an HTTP request from Dograh back into brokerAgent, where the guardrail decided whether to allow it.

Timestamps are seconds from the first utterance. Tool calls are placed after the turn whose content they acted on — their exact clock position was not recorded on these runs.

---

`0:00` **Asha**: Hi, am I speaking with Aditya?

`0:05` **Aditya**: Yes, this last.

`0:11` **Asha**: I am Asha from the rental desk in Gurugram calling about the home you enquired about. Is now a good time to talk?

`0:18` **Aditya**: Okay.

`0:22` **Asha**: Great! Just to confirm, your monthly rent budget is between ₹50,000 and ₹1,00,000, correct?

`0:32` **Aditya**: Make it make it 50 to 75 K.

> **🔧 HTTP tool call #1 — `capture_field`** · guardrail: allowed
> `POST /api/dograh/tools/capture_field` with `field="monthly_rent_min"`, `value="50000"`
> _Records one fact the caller stated, the moment they said it._

> **🔧 HTTP tool call #2 — `capture_field`** · guardrail: allowed
> `POST /api/dograh/tools/capture_field` with `field="monthly_rent_max"`, `value="75000"`
> _Records one fact the caller stated, the moment they said it._

`0:44` **Asha**: Thank you for the update. Your monthly rent budget is now ₹50,000 to ₹75,000. You mentioned earlier you prefer Sector 54 and a 2BHK. Is that still correct?

`1:02` **Aditya**: Yes.

`1:06` **Asha**: Thanks for confirming. Are you open to any furnishing preference for the 2BHK? Furnished, semi-furnished, or unfurnished?

`1:19` **Aditya**: Let's I I want it furnished, yeah.

> **🔧 HTTP tool call #3 — `capture_field`** · guardrail: allowed
> `POST /api/dograh/tools/capture_field` with `field="furnishing"`, `value="furnished"`
> _Records one fact the caller stated, the moment they said it._

> **🔧 HTTP tool call #4 — `search_properties`** · guardrail: allowed
> `POST /api/dograh/tools/search_properties` with `areas=["Sector 54"]`, `rent_min=50000`, `rent_max=75000`, `bhk="2BHK"`
> _Searches available listings against the captured requirement._

`1:32` **Asha**: Currently, I don't have any furnished 2BHK properties available in Sector 54 within ₹50,000 to ₹75,000 rent. I will check with owners and come back to you with options. Would you like me to notify you when I find something?

`1:51` **Aditya**: Yes, please notify me.

> **🔧 HTTP tool call #5 — `capture_field`** · guardrail: allowed
> `POST /api/dograh/tools/capture_field` with `field="preferred_areas"`, `value="near Sector 54"`
> _Records one fact the caller stated, the moment they said it._

> **🔧 HTTP tool call #6 — `search_properties`** · guardrail: allowed
> `POST /api/dograh/tools/search_properties` with `areas=["near Sector 54"]`, `rent_min=50000`, `rent_max=75000`, `bhk="2BHK"`
> _Searches available listings against the captured requirement._

`2:19` **Asha**: I checked for furnished 2BHKs near Sector 54 in your budget, but none are available

`2:24` **Aditya**: No no not not furnished I I am just looking for some property.

`2:38` **Asha**: Okay, so furnished is not compulsory. You are open to any furnishing for 2BHK near Sector 54 with rent ₹50,000 to ₹75,000, right?

`2:50` **Aditya**: Yeah. N furnish any furnished status is fine. Yeah.

> **🔧 HTTP tool call #7 — `capture_field`** · guardrail: allowed
> `POST /api/dograh/tools/capture_field` with `field="furnishing"`, `value="any"`
> _Records one fact the caller stated, the moment they said it._

> **🔧 HTTP tool call #8 — `search_properties`** · guardrail: allowed
> `POST /api/dograh/tools/search_properties` with `areas=["Sector 54", "near Sector 54"]`, `rent_min=50000`, `rent_max=75000`, `bhk="2BHK"`
> _Searches available listings against the captured requirement._

`3:02` **Asha**: I checked again for any 2BHK properties in or near Sector 54 within ₹50,000 to ₹75,000 rent, with any furnishing status. Unfortunately, there are no available properties right now. I will keep looking and notify you when I find some. Would that be okay?

`3:25` **Aditya**: Yes, that is fine. Thank you.

---

**18 turns · 8 tool calls · 0 refused by the guardrail**
