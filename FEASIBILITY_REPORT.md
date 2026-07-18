# Provider Expansion — Feasibility Report (Phase 3G redesign)

**Question (yours):** can the expanded, search-engine-style provider strategy realistically
reach *several thousand* active professional-tech events across India at ₹0, without
entertainment and without anti-bot bypass — or is it impossible?

**Verdict: NOT impossible — but it is CURATION-bound, not architecture- or mechanism-bound.**
Every ingestion *mechanism* works at ₹0 and the events *exist*; the one thing that does **not**
work at ₹0 is **automatic discovery** of the source list. So scale is a function of how many
source URLs get curated, not of engineering. Thousands is reachable with a curated catalog;
it is not reachable by flipping a switch.

## Method

Six read-only investigation spikes (in `backend/spikes/`), ~50 candidates across every
source *type* you named — not just "event platforms":
`probe_providers.py`, `probe_providers2.py`, `probe_structure.py`, `probe_ecosystem.py`,
`probe_meetup_ics.py`, `probe_discovery.py`, `probe_github_directories.py`.

## Evidence — what works, and where the wall is

| Source family | Mechanism at ₹0? | Auto-discovery at ₹0? | Evidence |
|---|---|---|---|
| **Bevy communities** (GDG, CNCF, Atlassian, Salesforce, Snowflake, …) | ✅ works (JSON API) | ❌ no directory — hosts must be guessed (3 hits / ~19 guesses) | 5 built, ~70 events |
| **Meetup groups (ICS)** | ✅ works — public `.ics` per group, clean events | ❌ **search is client-side GraphQL** — 0 groups from 20 topic×city searches | `probe_discovery.py` |
| **Generic ICS** (Google/Luma/community calendars) | ✅ works — parsed a 535-event calendar | ❌ calendar IDs not enumerable | `probe_ecosystem.py` |
| **RSS / newsletters** | ✅ works (25 items parsed) | ⚠️ per-feed, hand-listed | `probe_ecosystem.py` |
| **JSON-LD pages** (conf/community) | ✅ works for specific sites (Hasgeek) | ❌ per-URL, hand-listed | existing Hasgeek provider |
| **Hackathon APIs** (Devfolio, Devpost) | ✅ works (JSON) | ✅ built-in search | 2 built, ~22 events |
| **Aggregators** (allevents.in, 10times) | ⚠️ JSON-LD present | — | ❌ mix **entertainment/expos** — fails the quality bar |
| **Meetup search / GraphQL** | — | ❌ 404 / client-side | `probe_providers.py`, `probe_discovery.py` |
| **Curated GitHub directories** | ⚠️ list names/links, not feeds | partial bootstrap | `omrajsharma/tech-communities`, `zeospec/indiaconferences.tech` |
| **Meetup.com API / Eventbrite** | ❌ paid / OAuth | — | Pro-only; search API removed 2019 |

**The single decisive finding:** the mechanisms are easy; **discovery is the wall.** Meetup
(where most recurring India tech community events live) exposes a clean per-group ICS feed,
but its group *search* is client-rendered GraphQL — there is no ₹0 GET that enumerates the
hundreds of India tech groups. Guessing slugs yields ~40% 404s. Bevy has no directory.

## The redesign (built this turn) — a config-driven, hierarchical registry

The right architecture for "hundreds of small providers" is **generic source-type families +
a config catalog**, not one class per website:

- **`ICSProvider`** — one generic iCalendar parser; **each feed is its own provider** with its
  own id, city, category, health, and refresh interval (your hierarchical model).
- **`ics_sources.py`** — the curated catalog. *Adding a source is adding a line.* The registry
  loops over it (`build_registry()` → `_ics_plugin`), so 9 or 900 feeds need **no code change**.
- Same pattern extends to RSS and JSON-LD families (generic parser + URL list).

**Live proof:** 7 → **20 providers** (11 API + 9 ICS Meetup groups), **164 active events**,
41 cities, **20/20 healthy**, dedup 2.4%. Adding the 9 Meetup feeds was pure config.

## The bottleneck, quantified

Reaching thousands is now a **curation** problem:

- India tech Meetup groups number in the **hundreds** across ~10 metros (Python, JS, React,
  AWS UG, K8s, DevOps, Data Science, Cloud, Rust, Go, mobile, …). At a snapshot many have 0
  upcoming, but an active subset of, say, **300–500 curated groups × ~2 upcoming ≈ 600–1,000
  events**, refreshed continuously.
- Plus community Google/Luma calendars, university club calendars, and more Bevy communities.
- So **~1,000–2,000 active events is realistic with a curated catalog of ~400–800 sources.**
  **5,000+** would require either near-exhaustive Meetup curation or a paid discovery source.

The rate-limiter is the **human/research effort to find and confirm each source URL** (each
Meetup slug must be discovered + probed; ~40% of guesses 404). The architecture ingests them
for free once listed.

## Recommendation

1. **Keep the milestone.** It is not impossible — so per your instruction, do not revisit it.
2. **Grow `ics_sources.py` continuously.** This is the lever. I can keep curating source URLs
   over subsequent turns (probe-confirm batches of Meetup groups + community calendars + Bevy
   hosts), each turn adding dozens of confirmed feeds → the catalog climbs toward 1,000.
3. **Fastest accelerator:** if you can supply (or point me at) a curated list of India tech
   Meetup groups / community calendar URLs, curation cost collapses and 1,000+ arrives quickly.
   Otherwise I curate by probing, which is slower but works.
4. **Do NOT** add allevents.in/10times — they breach the "no entertainment" bar.

**Bottom line:** the strategy is sound and the architecture now scales to hundreds of sources
with zero code per source. Thousands of events is achievable; the work ahead is *curation
throughput*, which I'll keep grinding — this is not an engineering dead-end.
