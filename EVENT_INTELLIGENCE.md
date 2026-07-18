# Continuous Event Intelligence (Phase 4D)

The automation layer that turns EventScout from a searchable catalog into a **continuously
updating intelligence platform**. It monitors the ecosystem after every ingestion and
produces intelligence — change detection, freshness, lifecycle, trending, organizer/community
profiles, and analytics.

## Principle: a deterministic projection, zero coupling

The intelligence layer is a **projection over the frozen catalog + provider state + entity
graph**. It reads them; it mutates none of them. No provider, no scheduler, no search
component knows it exists. All time is passed in explicitly, so every computation is
**deterministic and reproducible** (proven by the tests + the two-run live verification).

Honest scope (the frozen `Event` model lacks fields): registration-deadline signals are
**proxied from `start_date`**; "cancelled" maps to the `withdrawn` status; **cross-provider
trending is unavailable** post-deduplication; growth is approximated from forward activity.
These are documented, not faked — they get real inputs with the Phase-5 Opportunity model.

## Modules (`app/intelligence/`)

| Module | Role |
|---|---|
| `changes.py` | **Event Change Detector** — new / updated / cancelled / expired + venue/cost/date changes, snapshot-vs-catalog |
| `freshness.py` | **Freshness Engine** — 0..1 score + recently-added / recently-updated / trending-soon / ending-soon |
| `lifecycle.py` | **Lifecycle Engine** + **Registration Deadline Monitor** — the five auto-updating states |
| `trending.py` | **Trending Engine** — deterministic signal blend; `EngagementSignal` plug-in for future user signals |
| `organizers.py` | **Organizer Intelligence** — profiles for organizers / communities / series |
| `community.py` | **Community Intelligence** — fastest-growing / most-active / recurring / inactive |
| `analytics.py` | **Intelligence Analytics** — the daily ecosystem report |
| `store.py` | **Intelligence Store** — storage-independent persistence (snapshot + report) |
| `hooks.py` | **Future Hooks** — notification/recommendation/alert **interfaces only** |
| `engine.py` | **Background Intelligence Pipeline** — orchestrates one run |

## The pipeline

```
Catalog Updated  (after a successful ingestion cycle)
   ▼  Detect Changes          (previous snapshot vs current catalog)
   ▼  Refresh Intelligence    (entity graph, lifecycle distribution, trending)
   ▼  Update Organizer Profiles
   ▼  Update Community Profiles
   ▼  Update Trending
   ▼  Update Analytics
   ▼  Persist Results         (new snapshot for next run + the report; notify hooks)
```

`IntelligenceEngine.run(repo, provider_states, now)` performs the whole pass. It is invoked
by an orchestrator **after** ingestion (a thin `run_cycle()` → `intelligence.run()`
sequence) — the frozen scheduler is neither modified nor aware of it.

## Lifecycle

```
UPCOMING → REGISTRATION_CLOSING → LIVE_TODAY → COMPLETED → ARCHIVED
```

A pure function of the event's dates + stored status + `now` (nothing is written back to the
Repository): archived (status or > `archive_after_days` past) · completed (ended) · live
(start ≤ today ≤ end) · registration-closing (starts within `registration_closing_days`) ·
upcoming (else). Live result over the real catalog: **6 live · 41 closing · 52 upcoming**.

## Scoring

- **Freshness** = 0.5·discovery-recency + 0.4·start-proximity + 0.1·updated (each a decay to
  `freshness_half_life_days`).
- **Trending** = 0.35·source-quality + 0.30·freshness + 0.20·popularity(content richness) +
  0.15·update-frequency(`version`) **+ Σ engagement signals** (0 today). Upcoming only,
  best-first, deterministic. Live top: FutureForge Hackathon (0.73), HackVSIT7.0 (0.72), …
- **Organizer quality** = mean event completeness.

## Analytics

New / updated / expired / cancelled today, venue changes, trending events, **active vs. stale
providers** (from the Provider State Store health), lifecycle distribution, and organizer/
community activity. See [INTELLIGENCE_ANALYTICS.md](INTELLIGENCE_ANALYTICS.md) for the fields
+ live numbers.

## Future integrations (interfaces only — nothing implemented)

`hooks.py` defines the extension points the pipeline will drive:
- `IntelligenceHook.on_report(report)` — the single hook the engine already invokes.
- `NotificationChannel` (+ `EmailAlert`, `WhatsAppAlert` markers), `Recommender`,
  `SavedSearchMatcher`, `CalendarReminder`.

A future notifier implements `IntelligenceHook`, reads the `ChangeSet`/trending/lifecycle from
the report, and dispatches through a `NotificationChannel` — **with no change to the engine or
anything frozen**. Recommendations and saved-search alerts plug in the same way. The
`EngagementSignal` interface lets user behavior (clicks/saves/applications) feed trending
later without touching the Trending Engine.

## Storage & scale

In-memory today (snapshot + report), behind `IntelligenceStore` so a SQLite/Postgres backend
drops in later. The engine currently **rebuilds** from the full catalog each run (fine at
10⁴–10⁵); an incremental change feed (from the ingestion outbox, once ingestion is unfrozen)
is the scale path. Everything is O(catalog) per run today; entity/graph work dominates.
