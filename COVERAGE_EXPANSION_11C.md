# Coverage Expansion — Phase 11C (toward 3,000)

**Goal:** grow from 1,032 to 3,000+ real, non-duplicate, upcoming India tech events.

**Result:** **1,032 → 1,823 active de-duplicated events (+791, 1.77×).** The 3,000 target was **not**
reached. This report documents the measured growth **and** the evidence for **stop-condition #2** — the
accessible public machine-readable ecosystem has been effectively exhausted at ~1,850; the remaining
~1,200 events to reach 3,000 sit behind JavaScript-rendered or auth-gated walls that a no-browser,
keyless architecture cannot cross without the "new architecture" you ruled out.

No new architecture. Growth came from **aggressively expanding the existing Meetup + Eventbrite
providers** (bigger keyword × city sweeps) — no new frameworks, no new engines.

## What was done

### 1. Meetup — expanded to 42 keywords × 20 cities (564 events)
- Widened the sweep from 20→**42 keywords** (AI, GenAI, ML, LLM, Python, JS, React, Node, Java, Go,
  Rust, Flutter, Android, DevOps, Docker, K8s, Linux, AWS, Azure, cybersecurity, blockchain, Web3, IoT,
  robotics, VR, game dev, UI/UX, product, startup, hackathon, open source, TensorFlow, LangChain, AI
  agents, PyData, …) and 16→**20 cities** (added Nagpur, Kochi, Thiruvananthapuram, Visakhapatnam).
- **Measured ceiling:** Meetup returned **564–568 unique upcoming events on every run** regardless of
  matrix size — this is the actual size of the upcoming India-tech Meetup pool, not a matrix limit.
  (Beyond ~840 requests Meetup begins rate-limiting, which *reduces* yield.)

### 2. Eventbrite — expanded to 22 keyword-scopes × 16 locations (758 events)
- Rebuilt from a single "technology" scope to a **keyword × location sweep** (technology, software,
  developer, AI, ML, data-science, hackathon, conference, engineering, startup, innovation, cloud,
  web-dev, cybersecurity, blockchain, devops, IoT, robotics, product, networking, python,
  developer-tools) × India + online + 14 city scopes.
- Added a **`.com`-only filter** (India events live on `eventbrite.com`; foreign-country domains that
  leaked into India search are dropped).
- **119 → 758 events** — the largest single gain this phase.

### 3. New providers — investigated, none usable (evidence below)
Every candidate you listed was probed live. **None expose machine-readable event data** to a
no-JavaScript, no-API-key client — so no new provider could be added; the growth is from expanding the
two providers that *do* work.

## Duplicate protection

Cross-provider dedup (the pipeline dedups only per-provider) was run after every ingestion:
- **Foreign-domain Eventbrite** rows removed (kept India `.com`).
- **Exact title+date cross-provider duplicates** removed (kept the richest) — 8, 6, 7 per run.
- Total **56 rows superseded** (auditable, not deleted). Net dup rate < 1%.

## Measured metrics

**By source:** Eventbrite **758** · Meetup **564** · Unstop 299 · Lu.ma 63 · Salesforce 30 · GDG 20 ·
Devfolio 17 · Atlassian 17 · FOSS United 16 · Hasgeek 9 · Devpost 8 · Snowflake 6 · confs.tech 4 · CNCF 1
· (+ legacy Meetup-ICS).

**By category:** conference 730 · meetup 498 · hackathon 267 · ai 125 · workshop 122 · startup 65 · webinar 16.

**Geography — 102 distinct cities** (was 70), **95 Tier-2/3**; online 877 / offline 946.
Bangalore 180 · Delhi 107 · Hyderabad 99 · Pune 72 · Mumbai 72 · Gurgaon 39 · Chennai 34 · Noida 23 ·
Ahmedabad 23 · Jaipur 22 · Coimbatore 13 · Kolkata 12 · Indore 8 · Nagpur 7 · … (Tier-2/3 long tail).

**Technologies (enrichment):** Python · AWS · Gemini · Claude · Java (16 technologies) ·
**Topics:** Artificial Intelligence, Startup, Product, Generative AI, Cloud (19 topics).

**New this phase:** +791 net events · +~150 new Meetup organizer groups · new city coverage +32 cities.

## Stop-condition #2 — evidence the accessible ecosystem is exhausted

| Candidate source (you listed) | Live probe result | Usable? |
|---|---|---|
| Konfhub | API 401/403 (auth key); site no JSON-LD | ❌ auth |
| Commudle | `api.commudle.com` 503; GraphQL 503; site is Angular | ❌ JS/blocked |
| Townscript | search API 401 | ❌ auth |
| Kommunity | JS-only shell, no embedded data | ❌ JS |
| Hack2Skill | API ConnectError; site no JSON-LD | ❌ JS |
| Confengine | 403 | ❌ blocked |
| dev.events | 200 but no JSON-LD (JS) | ❌ JS |
| Skillenza | ConnectError | ❌ down |
| Linux Foundation events | 200 but 0 JSON-LD (JS) | ❌ JS |
| GDG chapter directory API | 404 | ❌ |
| 10times | JS-rendered, 0 server-side events | ❌ JS |
| MLH / HackerEarth (11A) | not parseable / 3 events | ❌ negligible |
| 30 Bevy communities (11A) | only CNCF answers | ❌ exhausted |
| allevents.in | JSON-LD present, but an **aggregator** that re-lists events already indexed → **duplicates** (you forbade duplicates) | ❌ rejected |
| AWS / Google / Microsoft / NVIDIA / Oracle / Red Hat / MongoDB / Docker / GitLab / Vercel / Supabase event sites | all JavaScript-rendered SPAs | ❌ JS |

**The two accessible levers (Meetup, Eventbrite) are maxed:**
- Meetup returns ~**565 ± 4** on every run — the actual upcoming India-tech Meetup pool.
- Eventbrite returns ~**760** fresh; larger sweeps hit **rate-limiting** (200-with-captcha), *lowering*
  yield. Both were confirmed across 5 ingestion runs.

**Mathematical ceiling of accessible sources:** Meetup 565 + Eventbrite ~800 + Unstop ~300 + Lu.ma 63 +
Bevy/GDG/Devfolio/Devpost/Hasgeek/FOSS/confs ~230 ≈ **~1,900**, minus cross-provider dupes ≈ **~1,850**.
The catalog is at **1,823 — within ~1.5% of that ceiling.**

**Conclusion:** reaching 3,000 requires either (a) a **JavaScript-rendering tier** (browser/Playwright) to
read 10times, Commudle, and the corporate event SPAs, or (b) **API keys** (Konfhub, Townscript, Meetup at
scale, Eventbrite API), or (c) **aggregators** that introduce duplicates. All three are explicitly out of
scope ("no new architecture", keyless, no duplicates). **The public no-JS/no-auth/no-aggregator India tech
event ecosystem yields ~1,850 — that is the honest ceiling.**

## Honesty & quality notes

- **Real, not fabricated.** Every event is a live public page (Meetup group event, Eventbrite listing,
  Unstop hackathon…) with a real URL and upcoming date, ingested + validated by the existing pipeline.
- **Quality distribution (disclosed):** the `conference` category (730) is dominated by **Eventbrite**,
  which in India includes many **academic / professional conferences** (some low-signal "International
  Conference on…" listings). These are real, upcoming, public tech events but lower-signal than the
  community core. The high-signal core — Meetup community events (564) + Unstop hackathons (299) + Lu.ma /
  GDG / FOSS / Hasgeek (~120) ≈ **~985** — is where the community-event value concentrates.
- **Politeness:** Meetup/Eventbrite are live public pages read with capped concurrency; the aggressive
  sweeps triggered rate-limiting, which is itself the evidence of the ceiling.

## To actually reach 3,000 / 10,000 (requires a decision from you)

The only paths past ~1,850 cross a line this phase respected:
1. **A rendering tier** (headless browser) → unlocks 10times, Commudle, corporate event SPAs (JS-gated).
2. **API credentials** → Eventbrite API, Meetup GraphQL at scale, Konfhub, Townscript.
3. **Accept aggregators + heavy fuzzy dedup** → allevents.in etc. (duplicate risk you currently forbid).

Each is a deliberate architecture/policy choice — not something I'll add silently under "no new
architecture."

---

**Status:** 1,032 → **1,823** real, de-duplicated, India-focused searchable events (+791). Additive (2
providers expanded, 0 added — none were accessible); no architecture change; ingestion/search/frontend
untouched; backend suite **1034 green**; live app + homepage serve **1,823**. **Target 3,000 not reached —
stop-condition #2 (accessible ecosystem exhausted at ~1,850) documented with per-source evidence.**
