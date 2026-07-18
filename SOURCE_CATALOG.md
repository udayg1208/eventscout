# EventScout Source Catalog — India Professional Tech Event Ecosystems

Exhaustive research of every publicly accessible, ₹0, professional-tech-event-producing
ecosystem in India, grouped into **provider families**. Evidence: `backend/spikes/probe_*.py`
+ `research_sources*.py` (live probes). Legend below; **CONFIRMED** = probed live this phase.

**Scoring** — Quality ★1–5 (5 = pure curated professional-tech, 1 = noisy/mixed) ·
Maintenance Low/Med/High (effort to keep working; Low is best) · Difficulty
Trivial/Low/Med/High · Priority **P0** (built/immediate) → **P3** (low value or blocked).

---

## Executive summary — how large EventScout can realistically get

| Horizon | Sources | Active events (snapshot) |
|---|---|---|
| **Today (built)** | 20 providers | **164** |
| **Near-term** (this catalog's P0+P1) | ~120–180 | **~450–700** |
| **Full ₹0 curation ceiling** (all families exhausted) | **~300–500** | **~1,000–1,800** |
| "Several thousand" (3,000+) | — | ❌ needs paid Meetup/Eventbrite API or relaxed quality |

**Methodology:** counts are live-probed where marked CONFIRMED, else estimated from probed
yield × known ecosystem size.

> ## ⚠️ MEASURED REALITY (Phase 3G P0 — corrects the estimates below)
>
> P0 execution (see `COVERAGE_REPORT.md`) measured real yields **3–10× lower** than estimated,
> because the estimates conflated *events over a rolling window* with *concurrent upcoming*:
> - **Lu.ma:** at ceiling **40** concurrent (not ~100) — the 11 cities already capture it;
>   +9 cities measured **0 net**.
> - **Meetup ICS:** ~**0.2 events/source** concurrent — most India tech groups are idle at any
>   instant. Family concurrent yield ~16 (not 100–300).
> - **KonfHub:** **not keyless-viable** (SPA + authenticated API; no embedded/sitemap events).
>
> **Revised concurrent-upcoming ceiling at ₹0 with the quality bar: ~200–400 events**, not
> 1,000–1,800. The larger figure is only reachable as a **rolling-window** total (idle sources
> schedule over time). 500+ *concurrent* likely needs paid discovery or relaxed quality.

## Family overview

| Family | How published | Ingestion | Sources | Est. events | Quality | Maint | Diff | Priority |
|---|---|---|---|---|---|---|---|---|
| Bevy communities | JSON API `/api/event/` (all India chapters per host) | `BevyEventProvider` ✅ | ~8 | ~80 | ★★★★★ | Low | Trivial | **P0** |
| Lu.ma city pages | `__NEXT_DATA__` JSON | `LumaProvider` ✅ | ~12 | ~100 | ★★★★ | Med | Low | **P0** |
| Meetup groups | public `.ics` per group | `ICSProvider` ✅ | **200–500** | ~100–300 | ★★★★ | Med | Trivial/source | **P1** |
| Hackathon platforms | JSON API | Devfolio/Devpost ✅ | 3–4 | ~30 | ★★★★ | Med | Low | **P0** |
| India tech platforms | NEXT_DATA / JSON-LD / sitemap | new JSON-LD/NEXT provider | 4 | ~80–180 | ★★★–★★★★ | Med | Med | **P1** |
| Conference orgs | JSON-LD / curated data | Hasgeek/ConfsTech ✅ + JSON-LD | ~15 | ~40 | ★★★★★ | Med | Med | **P1** |
| OSS foundations | REST / Bevy / RSS | FOSS United/CNCF ✅ + RSS | ~6 | ~30 | ★★★★★ | Low | Low | **P1** |
| Community calendars | public Google Calendar `.ics` | `ICSProvider` ✅ | ~20–40 | ~20–60 | ★★★★ | Med | Trivial/source | **P2** |
| Universities (GDSC/IEEE/ACM/clubs) | mostly Instagram/own sites | — (structured feeds rare) | 100s | ~0–40 | ★★★ | High | High | **P3** |
| Government innovation | press/HTML, no feeds | — | few | ~0–10 | ★★★ | High | High | **P3** |
| Company event pages | anti-bot / paid | — (blocked) | — | 0 | — | — | — | **skip** |

---

## A. Bevy communities — **P0** (each host = ALL its India chapters, one provider)

> Key fact: the Bevy `/api/event/` endpoint returns every chapter's events; **one source
> covers "every GDG chapter in India"** — no per-chapter fan-out needed.

| Source | URL | Discovery | Ingestion | Refresh | Est. events | Q | Maint | Diff | Prio |
|---|---|---|---|---|---|---|---|---|---|
| GDG (+ GDG On Campus / GDSC) | gdg.community.dev | CONFIRMED | Bevy JSON | 3h | 15 | ★★★★★ | Low | ✅ built | P0 |
| CNCF (KCDs, chapters) | community2.cncf.io | CONFIRMED | Bevy JSON | 3h | 1 | ★★★★★ | Low | ✅ built | P0 |
| Atlassian ACE | ace.atlassian.com | CONFIRMED | Bevy JSON | 3h | 17 | ★★★★ | Low | ✅ built | P0 |
| Salesforce Trailblazer | trailblazercommunitygroups.com | CONFIRMED | Bevy JSON | 3h | 27 | ★★★★ | Low | ✅ built | P0 |
| Snowflake User Groups | usergroups.snowflake.com | CONFIRMED | Bevy JSON | 6h | 6 | ★★★★ | Low | ✅ built | P0 |
| *candidates* (probe for India yield) | e.g. more Bevy hosts | needs probe | Bevy JSON | — | ~10–20 | ★★★★ | Low | Trivial | P2 |

Note: `community.aws` (AWS) 403s, MongoDB/Postman 404, HashiCorp/Twilio/UiPath DNS/SSL —
**no more easy Bevy hosts confirmed** (most US-centric). Realistic Bevy ceiling ~80 events.

## B. Lu.ma city pages — **P0** (highest untapped volume; existing provider under-harvests)

| Source | URL | Discovery | Ingestion | Est. events | Q | Prio |
|---|---|---|---|---|---|---|
| Lu.ma Bangalore | lu.ma/bangalore | **CONFIRMED ~60** | NEXT_DATA | ~60 | ★★★★ | P0 |
| Lu.ma Delhi | lu.ma/delhi | **CONFIRMED ~30** | NEXT_DATA | ~30 | ★★★★ | P0 |
| Lu.ma Mumbai | lu.ma/mumbai | **CONFIRMED ~30** | NEXT_DATA | ~30 | ★★★★ | P0 |
| Lu.ma Goa / Hyderabad / Pune / Chennai / Kolkata | lu.ma/{city} | CONFIRMED reachable (cycle) | NEXT_DATA | ~20 | ★★★★ | P1 |

Current `LumaProvider` harvests ~40; full India-city coverage → **~100–120** (net after dedup).
Action: extend the provider's curated city list (config, no code change).

## C. Meetup groups (ICS) — **P1** (the big fan-out; each group = one `.ics` source)

Discovery is **not automatable** (Meetup search is client-side GraphQL; curated GitHub lists
are resource-lists, not source-lists). So this family grows by **curating slugs** into
`ics_sources.py`. Confirmed hit-rate on *informed* slugs ≈ **49% reachable**, ~17% with current
events (they cycle). Universe ≈ **200–500** India tech groups.

**CONFIRMED reachable sources (probe this phase — catalog entries):**

| With current events | Reachable (idle, cycle in) |
|---|---|
| bangpypers (10), ReactJS-Bangalore, aws-user-group-hyderabad, Bangalore-Kubernetes-Meetup, docker-bangalore, PyData-Mumbai, javascript-meetup-bangalore | pydelhi, chennaipy, PythonPune, hyderabad-python-meetup-group, awsugblr, DevOps-Bangalore, Deep-Learning-Bangalore, Blrdroid, flutter-bangalore, Bangalore-Golang-Meetup, wordpress-bangalore, women-who-code-bangalore |

Ingestion `ICSProvider` ✅ · refresh 6h · Quality ★★★★ · Maint Med (Meetup could change ical) ·
Difficulty Trivial per source (one config line). **Estimated family yield at full curation:
~100–300 events.** Sub-topics to curate across ~10 metros: Python, JS/TS, React/Angular/Vue,
Node, Java/Kotlin, Android/iOS/Flutter, Go/Rust, AWS/Azure/GCP UGs, Kubernetes/Docker/DevOps,
Data/ML/AI, Blockchain, Cybersecurity, Salesforce, Product/UX.

## D. India tech event platforms — **P1** (newly discovered this phase)

| Source | URL | Discovery | Ingestion | Est. events | Q | Maint | Diff | Prio |
|---|---|---|---|---|---|---|---|---|
| ~~KonfHub~~ | konfhub.com | **SKIP (P0.3 measured)** — SPA + **authenticated** API; homepage NEXT_DATA=`{signedIn}`, 0 JSON-LD Events, sitemap = marketing pages only | — | 0 | — | — | — | **skip** |
| **Commudle** | commudle.com (+ sitemap.xml ~19 urls) | **CONFIRMED sitemap** | sitemap crawl → per-event JSON-LD | ~20–50 | ★★★★ | High (SPA) | High | P2 |
| Townscript | townscript.com/discover/all/technology | **CONFIRMED JSON-LD** | JSON-LD, tech-filter | ~10–40 | ★★★ (mixed) | Med | Med | P2 |
| MeraEvents | meraevents.com (tech cat) | **CONFIRMED JSON-LD** | JSON-LD, tech-filter | ~10–30 | ★★ (ticketing, mixed) | Med | Med | P3 |
| Kommunity | kommunity.com | reachable (needs parse probe) | NEXT/JSON | ? | ★★★ | Med | Med | P3 |

## E. Hackathon platforms — **P0**

| Source | Ingestion | Est. | Q | Prio |
|---|---|---|---|---|
| Devfolio | JSON API ✅ built | 16 | ★★★★ | P0 |
| Devpost (search=india) | JSON API ✅ built | 6 | ★★★ | P0 |
| Unstop | SPA — **deferred** (undocumented API) | ~20–40 if solved | ★★★★ | P2 |
| HackerEarth challenges | JSON-LD (probe) | ~10 | ★★★ | P3 |

## F. Conference organizers — **P1**

| Source | URL | Ingestion | Est. | Q | Prio |
|---|---|---|---|---|---|
| Hasgeek (Rootconf, Fifth Elephant, JSFoo, …) | hasgeek.com | JSON-LD ✅ built (all projects) | 6–20 | ★★★★★ | P0 |
| Confs.tech (India entries, 29 topics) | GitHub `tech-conferences/conference-data` | JSON ✅ built | 4–11 | ★★★★★ | P0 |
| PyCon India / DjangoCon / JSFoo / RustConf / GopherCon India | individual sites | JSON-LD per-site | ~1–5 each | ★★★★★ | P2 |

## G. Open source foundations — **P1**

| Source | Ingestion | Est. | Prio |
|---|---|---|---|
| FOSS United (chapters) | Frappe REST ✅ built | 14 | P0 |
| CNCF | Bevy ✅ built | 1 | P0 |
| Python Software Foundation (python.org/events, India subset) | RSS/ICS (real feed URL TBD) | ~2–5 | P2 |
| Linux Foundation events | Cvent — **hard/blocked** | — | P3 |

## H. Community calendars (public Google Calendar `.ics`) — **P2**

Generic ICS parsing **CONFIRMED** (a Google Calendar returned 535 VEVENTs). Many communities
publish a public `.ics`; **discovery is manual** (find the calendar ID). Ingestion `ICSProvider`
✅ (already generic — add the URL to `ics_sources.py`). Est. ~20–60 events across ~20–40 feeds.

## I–K. Low-yield / blocked (documented, mostly skip)

| Family | Reality |
|---|---|
| Universities — GDSC / GDG On Campus | **already covered** by the GDG Bevy feed (no separate work) |
| Universities — IEEE / ACM student branches, coding clubs | 100s exist but publish on Instagram/PDF/own sites — **no structured feeds**; High difficulty, ~0 structured yield → **P3/skip** |
| Government innovation (MeitY, Startup India, T-Hub, state missions) | press-release/HTML, no event feeds → **P3/skip** |
| Company event pages (Google/Microsoft/AWS/Meta/…) | anti-bot or paid (`community.aws` 403; Meetup Pro/Eventbrite paid) → **skip** |
| Aggregators (allevents.in, 10times) | JSON-LD but **mix entertainment/expos** — breach the quality bar → **skip** |

---

## Total reachable volume (deduped snapshot)

| Family | Near-term | Ceiling |
|---|---|---|
| Bevy | 66 (built) | ~80 |
| Lu.ma | 40 (built) → ~100 | ~120 |
| Meetup ICS | ~20 (built) → ~60 | ~100–300 |
| Hackathon (Devfolio/Devpost) | 22 (built) | ~40 |
| India platforms (KonfHub/Commudle/Townscript) | ~60 | ~150 |
| Conference orgs (Hasgeek/ConfsTech/+JSON-LD) | ~15 (built) | ~50 |
| OSS foundations (FOSS United/CNCF/+PSF) | ~15 (built) | ~35 |
| Community calendars (ICS) | 0 | ~40 |
| **Total (deduped)** | **~450–700** | **~1,000–1,800** |

**Answer to "how large can EventScout become":** a credible **~1,000–1,800 concurrent quality
professional-tech events** across India at ₹0 — the largest *quality-first* catalog achievable
without paid discovery. Growth is curation-paced, and the architecture (config-driven
`ICSProvider` + family providers) ingests every added source for free.

## Prioritized implementation roadmap (>300 sources → highest value first)

- **P0 — DONE + MEASURED** (net **+4** events, not the estimated ~+110):
  1. ✅ Bevy ×5, Devfolio, Devpost, FOSS United, Hasgeek, Confs.tech, Meetup ICS (built).
  2. ~~Lu.ma full India cities~~ — **measured 0 net → reverted, closed** (already at ceiling 40).
  3. ~~Curate Meetup slugs~~ — **+4 net measured → family closed** (≈0.2 events/source concurrent;
     10 sources added + kept, but no further curation — below the coverage-per-effort bar).
  4. ~~KonfHub~~ — **skip** (SPA + authenticated API; not keyless-viable).
- **P1 — reframe target first (see `COVERAGE_REPORT.md`), then, if pursued:**
  5. **Generic JSON-LD provider** over a curated conference-site URL list (PyCon India, JSFoo…).
     Expected small incremental (+~20–40), measure per source.
  6. **Commudle** (sitemap crawl → per-event JSON-LD) — India-native, P2 effort. Measure.
- **P3 — low structured yield / blocked** (document, don't build): IEEE/ACM/university clubs,
  government portals, company pages, aggregators.

**Realism update:** the accessible ₹0 quality families are largely built; remaining P1/P2
sources add tens (measured), not hundreds. The concurrent ceiling is ~200–400. Implementation
of P1 continues **after** your review of this catalog + `COVERAGE_REPORT.md`.
