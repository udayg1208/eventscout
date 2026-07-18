# Data-Flow Audit — the 164 vs 96 discrepancy

Full end-to-end trace of the EventScout pipeline, with **real measured counts** (no
guessing — instrumented via `backend/spikes/audit_pipeline.py` and `audit_trace.py`).

## TL;DR

There was **no event loss in the pipeline**. Every stage from Database → Search Index →
Search → API reports the **same** number on a given catalog (proven: all 164 on a fresh
run). The discrepancy was **two different datasets**:

- **96** = the persisted `catalog.db` the API/UI reads — seeded **once** during the Phase-6B
  demo with the original **7** providers, and **never re-ingested** after Phase 3G added 13
  new providers.
- **164** = a **throwaway in-memory** verification run (`spikes/m3g_verify.py` uses
  `SQLiteEventRepository()` with no path = `:memory:`) that **never wrote to `catalog.db`**.

**Fixed** by rebuilding the catalog projection from the providers (the true source of truth)
and restarting the API. All five counts now equal **164**.

## 1. Architecture diagram

```
                              ┌─────────────── WRITE PATH (ingestion) ───────────────┐
 Providers (20)   →  Ingestion Runner  →  normalize → classify → entity-resolve → bulk_upsert
 (Bevy/API/ICS)        run_ingestion()      (stages.py, deterministic)                 │
                                                                                        ▼
                                                            ┌───────────────────────────────┐
                                                            │   catalog.db  (SOURCE OF TRUTH)│
                                                            │   get_repository() — config    │
                                                            │   path "catalog.db"            │
                                                            └───────────────────────────────┘
                              ┌─────────────── READ PATH (serving) ─────────────────┐  │
                              ▼                                                          │
   Frontend UI  ←  HTTP API  ←  PlatformService (singleton, built once)  ←  iterate(active_only)
   (analytics    /platform/*     ├─ DatabaseSearchProvider → SearchIndex (FTS, projection)
    stat = 164)                  └─ analytics.total = len(active events)
```

**Both write and read paths use the SAME `catalog.db`** (`get_repository()`, config
`catalog_db_path`). The bug was operational: the write path was never re-run into it after
the providers were added, and the read path caches its view at startup.

## 2. Event counts at every stage (instrumented, `audit_trace.py`, fresh catalog)

| # | Stage | Entered | Left | Filtered | Why / which code |
|---|---|---|---|---|---|
| 1 | Provider fetch (raw) | — | **175** | — | each provider is India+upcoming-scoped at source |
| 2 | Ingestion validate | 175 | 168 | −7 | `stages.validate_events` drops empty-title / already-ended (intentional) |
| 3 | Self-dedup + cross-source resolve | 168 | **164** | −4 | `stages.self_dedupe` + `runner._resolve` vs DB (intentional) |
| 4 | Repository `bulk_upsert` (inserted) | 164 | 164 | 0 | `SQLiteEventRepository.bulk_upsert` (key = `event_key`) |
| 5 | Database — total / **active** | 164 | **164** | 0 | — |
| 6 | Search Index — indexed docs | 164 | **164** | 0 | `DatabaseSearchProvider._ensure_projections` → FTS5 |
| 7 | Search Provider — broad results | 164 | **164** | 0 | bounded by `candidate_limit=500` (>164 → no cut) |
| 8 | Platform API — `analytics.total` | 164 | **164** | 0 | `PlatformService.analytics()` = len(active) |
| 9 | Frontend UI — "Events" stat | 164 | **164** | 0 | landing reads `/platform/analytics` |

**`DB active == index == API == frontend == 164`.** No stage between the catalog and the UI
loses anything.

## 3. Every place events CAN be filtered (all intentional, verified)

1. **Provider `search()`** — India + upcoming only (e.g. Bevy `country==IN & start>=today`;
   Devfolio `country=="India"`; ICS from a curated India group).
2. **`stages.validate_events`** — rejects empty-title / already-ended events (the 7 above).
3. **`stages.self_dedupe` + `runner._resolve`** — cross-source dedup by `event_similarity`
   (the 4 above).
4. **`to_criteria` / repository `search`** — scopes to `active_only` + `date_from=today`.
5. **`candidate_limit=500`** (search) — ranking window; no effect below 500.
6. **API endpoint `limit ≤ 100`** — pagination cap on `discover`/`browse`/`search` (display,
   not loss — the catalog still holds all 164; the frontend paginates with "Load more").
7. **Homepage `per_section`** — display slice per row (not loss).
8. **`PlatformService.from_repository`** — loads `active_only` (expired/archived excluded — a
   correct lifecycle decision, not loss).

## 4. Every place events CAN disappear (the real failure modes)

| Mechanism | Present here? | Effect |
|---|---|---|
| **Stale persisted `catalog.db`** (write path not re-run) | ✅ **THE root cause** | UI froze at 96 |
| **Cached `PlatformService` singleton** (built once at first request, no post-ingestion invalidate) | ✅ secondary | even after re-seed, needs restart |
| **Cached search projections** (FTS+graph, `_ready` flag, built once) | ✅ secondary | same |
| Measuring an in-memory DB instead of `catalog.db` | ✅ **the "164" source** | 164 never persisted for the UI |
| Multiple/zombie server instances (a `--reload` worker rebuilt from a **mid-ingestion** catalog → served 115/6) | ✅ observed during fix | transient wrong counts |
| Search index out of sync with catalog | ❌ (it's a build-time projection; synced on (re)start) | — |
| Frontend querying an old/other repository | ❌ (same `catalog.db`; it was a stale in-memory snapshot) | — |

## 5. Root cause

`catalog.db` is the single source of truth for the read path. It was materialized **once** by
`spikes/seed_catalog.py` during the Phase-6B demo, when only the **7 original providers**
existed → **96 events**. Phase 3G then added **13 providers** (4 API + 9 ICS) to the code, but
**ingestion was never re-run into `catalog.db`**. The only place the full **164** appeared was
`spikes/m3g_verify.py`, which ingests into an **in-memory** repository (`SQLiteEventRepository()`
with no path) and never persists. So 96 (persisted, old) vs 164 (in-memory, throwaway) were
**two different databases**, not two ends of a lossy pipeline. A secondary layer: the running
API builds its `PlatformService` + search projections **once at startup** and caches them, so
the UI would stay at 96 until the server is restarted even if `catalog.db` were refreshed.

## 6. Exact fix (operational — no architecture change)

The catalog is a **projection of the providers** (fully rebuildable), so the fix is to rebuild
it and restart the reader:

```bash
# 1. stop the API (release catalog.db)
# 2. delete the stale projection + provider state (rebuildable from source)
rm backend/catalog.db backend/provider_state.db
# 3. re-ingest ALL providers into catalog.db (the write path)
python -m spikes.seed_catalog          # -> "catalog seeded: 164 active / 164 total"
# 4. restart the API (rebuilds the PlatformService singleton + search index from catalog.db)
uvicorn app.main:app --host 127.0.0.1 --port 8000    # NOT --reload
```

(During the fix a stray `--reload` worker was serving a mid-ingestion snapshot (115/6) and a
respawning reloader held the port; clearing all Python processes and starting a single
non-reload server produced a clean, deterministic result.)

## 7. Verification after the fix (all five match)

| Stage | Measured | Source |
|---|---|---|
| **Ingestion** accepted | **164** | `seed_catalog` → "164 active / 164 total" |
| **Database** active | **164** | `audit_pipeline.py` on `catalog.db` (14 providers with events) |
| **Search** index docs | **164** | `audit_trace.py` (`_index.count()`) |
| **API** `analytics.total_events` | **164** | live `GET /platform/analytics` (providers=14, cities=41) |
| **Frontend** "Events" stat | **164** | rendered UI on `localhost:3000` (Cities 41, Sources 14) |

**One consistent event count across the entire pipeline: 164. ✅**

## Recommendation (for production single-source-of-truth — architectural, not done here)

The manual "re-seed + restart" is only needed because the read side is **build-once**. For
continuous operation, after each ingestion cycle the orchestrator should call
`DatabaseSearchProvider.invalidate()` and refresh/rebuild the `PlatformService` projection
(the invalidate hook already exists; it is simply not wired to run post-ingestion). That would
make the catalog the live single source of truth with no restart. Left as a proposal per the
"do not change the architecture" constraint.
