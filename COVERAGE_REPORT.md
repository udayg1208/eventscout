# Coverage Report — Phase 3G P0 execution

Real, ingestion-measured results of the P0 roadmap (Lu.ma → Meetup ICS → KonfHub). No
estimates. Measured via `spikes/m3g_verify.py` (fresh full ingestion) after each step, then
persisted to `catalog.db` and verified on the live API.

## Headline

| Metric | Start of P0 | End of P0 |
|---|---|---|
| Active events | 164 | **168 (+4 net)** |
| Registered providers | 20 | **30** (18 producing events) |
| Cities | 41 | 41 |
| Categories | 7 | 7 |
| Duplicate rate | 2.4% | 2.4% |
| Provider health | 20/20 | **30/30 healthy** |
| Live pipeline (ingestion = DB = API) | — | **168 = 168 = 168 ✅** |

**P0 delivered +4 net events — far below the catalog's optimistic estimate.** The honest,
important finding is in "Reality vs estimate" below.

## Per-step measurements

### P0.1 — Lu.ma city expansion → **0 net events → REVERTED, family closed**
- Added 9 more India cities + slug variants (`bangalore`, `delhi`, kochi, indore, chandigarh,
  coimbatore, nagpur, noida, trivandrum) to the existing 11.
- **Measured:** Lu.ma yield stayed **exactly 40 → 40** (0 net). The existing 11 cities already
  capture Lu.ma's real India tech events; the research "~60/~30" figures were inflated
  raw-HTML reference counts, not unique events.
- **Action:** reverted to the lean 11-city list (kept fetches minimal). Coverage-per-effort:
  **zero → stop.** Maintenance risk: Medium (`__NEXT_DATA__` shape could change).

### P0.2 — Meetup ICS family → **+4 net events → family closed (below threshold)**
- Added 10 probe-confirmed reachable Meetup groups to `ics_sources.py` (config only).
- **Measured (164 → 168):** 4 new sources had current events — `ReactJS-Bangalore`,
  `docker-bangalore`, `PyData-Mumbai`, `javascript-meetup-bangalore` (each +1). The other 6
  (`PythonPune`, `hyderabad-python-meetup-group`, `Deep-Learning-Bangalore`, `Blrdroid`,
  `wordpress-bangalore`, `women-who-code-bangalore`) were reachable but **idle** (0 upcoming).
- **Coverage-per-effort:** +4 net for ~10 trivial config lines = **below the 5-net threshold →
  stop expanding this family.** Snapshot yield ≈ **0.2 events/source** (most India tech Meetup
  groups have no upcoming event at any given moment). The 10 sources are **kept** — they cost
  nothing and cycle in events when those communities schedule. Maintenance risk: **Medium**
  (Meetup could remove/change the public `.ics` endpoint; 19 ICS sources to monitor).

### P0.3 — KonfHub → **NOT keyless-viable → SKIP**
- **Measured:** homepage `__NEXT_DATA__` = `{signedIn}` only; JSON-LD has **0 Event** nodes;
  `api.konfhub.com` → 401/403; `konfhub.com/sitemap.xml` → 131 URLs but all **marketing pages**
  (`/`, `/events`, `/features`, `/pricing`), no per-event pages. Events load client-side from an
  **authenticated** API. The earlier "NEXT_DATA + JSON-LD" signal was the SPA shell, not data.
- **Decision:** not accessible at ₹0 → **skip** (0 events). A sitemap/per-event-JSON-LD path
  does not exist; a private-API path needs auth (out of scope).

## Aggregate (final, live-verified)

- **168 active events**, 30 providers (30/30 healthy), 41 cities, 7 categories, dup 2.4%.
- By provider: luma 40 · salesforce 27 · atlassian 17 · devfolio 16 · gdg 15 · fossunited 14 ·
  meetup-bangpypers 10 · hasgeek 6 · devpost 6 · snowflake 6 · confs.tech 4 · (5 meetup-ICS at 1
  each) · cncf 1.
- Categories: meetup 100 · hackathon 25 · ai 19 · conference 12 · workshop 7 · startup 3 · webinar 2.

## Reality vs estimate — the critical finding

`SOURCE_CATALOG.md` estimated Lu.ma ~100, Meetup ~100–300, KonfHub ~30–60 (total ceiling
~1,000–1,800). **Real measurements are 3–10× lower:** Lu.ma is at its ceiling (40), the Meetup
family's *concurrent* snapshot yield is ~16 (not hundreds — most groups are idle at any
instant), and KonfHub is inaccessible.

**Root reason:** the estimates conflated *events over a rolling window* with *concurrent
upcoming events*. At any single moment, the number of **upcoming** professional-tech events in
India reachable at ₹0 with the quality bar appears to be **~200–400**, not 1,000+. The catalog
grows over a rolling window as idle sources schedule, but the concurrent count is bounded.

**Implication for the 500+ target:** 500 *concurrent* upcoming events is likely **not reachable
at ₹0** with the quality bar via the accessible families — it would need paid discovery
(Meetup Pro/Eventbrite) or the rejected low-quality aggregators. This should be confirmed and
the target reframed (e.g., "≥500 events over a rolling 90-day window", which is achievable) —
**a decision for you before P1.**

## Recommendation

- **Stop P0 here** (all three steps executed + measured; two families closed on the <5-net
  rule, one skipped as inaccessible).
- **Before P1**, reframe the target to a rolling-window metric OR accept ~200–400 concurrent as
  the ₹0 quality ceiling. P1 sources (Commudle sitemap-crawl, a generic JSON-LD conference-site
  provider, Unstop) would add incremental concurrent events (~+20–60 total, measured), not
  hundreds.
