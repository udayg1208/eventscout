# Coverage Expansion — Phase 11B

**Objective:** increase EventScout's searchable catalog toward 1,000+ real, non-duplicate public tech
events (Phase 1 of the 1k → 3k → 10k roadmap).

**Result:** **505 → 1,032 active searchable events (+527, 2.0×).** Stop-condition **(A) exceeded 1,000**
is met. Every event originates from a real, publicly accessible page; nothing was fabricated; duplicates
were removed.

No new architecture was added — only two new **providers** on the existing `EventProvider` interface
(the same mechanism as the Unstop provider), plus the existing ingestion/dedup pipeline.

## Where every new event came from (measured)

The +527 net-new events came from two newly-added primary sources, discovered by probing the public web:

### 1. Meetup — 414 events (the biggest lever)
- **Source:** the **public** Meetup find page embeds its search results as Next.js `__NEXT_DATA__` JSON —
  the *exact same public-page-JSON technique the existing Lu.ma provider already uses*. No API key, no
  login, no private endpoint.
  `GET https://www.meetup.com/find/?keywords=<kw>&location=in--<City>&source=EVENTS`
- **Method:** a **20 keyword × 16 city** sweep (`app/providers/meetup.py`). Keywords span the ecosystems
  you listed (AI, ML, Python, DevOps, data science, cybersecurity, web, cloud, blockchain, JS, robotics,
  Flutter, React, IoT, Kubernetes, game dev, GenAI, startup, product); cities span metros + Tier-2/3
  (Noida, Gurgaon, Jaipur, Indore, Coimbatore, Chandigarh, Lucknow, Bhubaneswar…). Meetup's location
  search covers a regional radius, reaching surrounding ecosystems.
- **Discovered 307 distinct Meetup organizer groups** (e.g. `building-from-zero-bengaluru`,
  `gurgaon-electronics-meetup`, `bitshala`, `producttank-chandigarh`, `primewise-founders-club-chennai`)
  — real communities that publish only on Meetup and were previously invisible to EventScout.
- Deduped by event URL within the provider; upcoming-only.

### 2. Eventbrite — 119 events
- **Source:** Eventbrite's **public** discovery pages embed results as `window.__SERVER_DATA__` JSON
  (same technique). `GET https://www.eventbrite.com/d/<scope>/` for India + Tier-2/3 city scopes
  (`app/providers/eventbrite.py`).
- Organizers post directly (a primary source → low overlap with the community platforms already indexed).
- **48 foreign-country Eventbrite events** (on `eventbrite.co.uk/.com.au/.sg/.ie/.ca/…`, i.e. non-India)
  that leaked into India-scoped search were **removed** — the catalog is kept India-focused.

The other +38 came from the existing Unstop provider (fresh upcoming listings) and the wider crawl.

## Duplicate protection (you said: DO NOT duplicate)

The ingestion pipeline dedups **per-provider** (URL + fuzzy title/date), but there is no cross-provider
dedup, so a cross-listed event could appear twice. I measured and removed cross-provider duplicates:
- **0 duplicate URLs** across providers.
- **3 exact title+date duplicate groups** (a global PyData event listed by 3 chapter ICS feeds; two
  events cross-posted on Luma/Eventbrite + Meetup) → **4 redundant rows removed** (kept the richest).
- Net dup rate before cleanup: **0.4%**. After cleanup: **0 exact cross-provider duplicates remain.**

Removed rows are marked `status='superseded'` (auditable, not deleted). Total superseded: 52 (4 dupes +
48 foreign).

## Measured coverage

**By source (provider):**
| Source | Events | New this phase |
|---|---:|:--:|
| Meetup (find-page) | 414 | ✅ NEW |
| Unstop | 299 | (11A) |
| Eventbrite | 119 | ✅ NEW |
| Lu.ma | 61 | |
| Salesforce / GDG / Devfolio / Atlassian / FOSS United | 100 | |
| Hasgeek / Devpost / Snowflake / confs.tech / CNCF / Meetup-ICS | 39 | |

**By category:** meetup 364 · hackathon 261 · conference 144 · ai 114 · workshop 84 · startup 54 · webinar 11.

**By technology (enrichment):** AWS 18 · Gemini 10 · Python 9 · Claude 5 · Azure 3 (14 technologies).
**By topic:** Artificial Intelligence 203 · Startup 85 · Product 24 · Generative AI 17 · Cloud 15 (19 topics).

**By geography:** **70 distinct cities** (was ~45), online 450 / offline 582.
- Metros: Bangalore 110 · Delhi 68 · Hyderabad 54 · Pune 50 · Mumbai 41 · Chennai 17 · Kolkata 9.
- **Tier-2/3 newly strengthened:** Jaipur 20 · Ahmedabad 15 · Gurgaon 14 · Noida 12 · Coimbatore 9 ·
  Indore 8 · Gandhinagar 4 · Greater Noida 3 · Thiruvananthapuram 3 · Vadodara/Salem/Lucknow/Kochi/
  Kalyani/Gwalior/Ghaziabad/Faridabad/Chandigarh/Bhilai/Puducherry (2 each) — **63 Tier-2/3 cities** covered.

**New domains discovered this phase:** `meetup.com`, `eventbrite.com` (48 distinct domains total).
**New organizers discovered:** **307** distinct Meetup groups + ~119 Eventbrite organizers.
**New event pages / validated events:** **+527 net** (581 gross ingested − 4 dupes − 48 foreign − ICS aging).

## Sources probed but NOT usable (evidence — no data invented)

To honor "prove exhaustion with evidence," these were probed live and found inaccessible without
crossing a line the architecture forbids (JS rendering / auth / duplicates):

| Source | Probe result |
|---|---|
| Konfhub | API returns **401/403** (auth key required); landing page has no JSON-LD |
| Commudle | `api.commudle.com` **503**; `www` path serves an Angular app (no JSON) |
| Townscript | search API **401** (auth required) |
| Kommunity | JS-only app (7 KB shell, no embedded data) |
| 10times | JS-rendered; **0** JSON-LD events server-side |
| allevents.in | JSON-LD present but it's an **aggregator** — re-lists events already sourced directly → would create duplicates (rejected) |
| Meetup GraphQL | endpoint **404** for logged-out clients |
| Lu.ma discover API | **404** (only the 11 city pages the existing provider already reads are exposed) |
| Bevy communities (30 hosts) | only the already-wired CNCF responds; rest 403 / not-Bevy (11A) |
| University / GitHub / Notion / Discord / Telegram / LinkedIn | no machine-readable event feeds; auth/JS-gated |

## Honesty notes

- **Real, not fabricated.** Every event is a live public page (Meetup group event, Eventbrite listing,
  etc.) with a real URL and date, ingested through the existing pipeline and validated (upcoming, has
  title). No synthetic data.
- **Eventbrite quality caveat:** Eventbrite's India tech feed includes some academic/"international
  conference" listings; these are real public pages but lower-signal. Foreign-domain events were removed;
  the rest are kept as real India-relevant listings.
- **Meetup is a live, polite sweep** (concurrency-capped, daily refresh). At much larger scale Meetup may
  rate-limit; the current matrix runs cleanly (~320 requests, ~50 s, no blocking observed).

## Toward Phase 2 (3,000) / Phase 3 (10,000)

The Meetup keyword×city matrix is the scalable lever — widening keywords (embedded, AR/VR, Rust, Go,
Android/iOS, UI/UX, Web3) and cities (every Tier-2/3 hub) linearly grows coverage. Eventbrite scopes can
be widened similarly. Reaching 3k–10k will also need the JS-gated sources (Commudle, 10times, Konfhub via
key, Meetup at scale), which require either a rendering tier or API credentials — a deliberate future
decision, not this phase.

---

**Status:** 1,032 real, de-duplicated, India-focused searchable events (from 505) — **target A met.**
Additive (2 providers); no architecture change; ingestion/search/frontend untouched; backend suite 1034
green. The running app at `http://localhost:3000` reflects the full catalog — the homepage headline
reads **"Events 1,032"** (verified live).
