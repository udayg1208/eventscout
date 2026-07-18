# Intelligence Analytics (Phase 4D)

What the Continuous Event Intelligence engine produces each run, with live numbers from the
real catalog (`spikes/m4d_intelligence.py`). All figures are deterministic given the catalog
state, provider states, and `now`.

## The analytics report

`build_intelligence_analytics(...)` → a dict with:

| Field | Meaning | Source |
|---|---|---|
| `new_events_today` | newly discovered since last run | Change Detector |
| `updated_today` | content changed since last run | Change Detector |
| `expired_today` | ended since last run | Change Detector (status → expired) |
| `cancelled_today` | withdrawn by source since last run | Change Detector (status → withdrawn) |
| `venue_changes_today` | location changed on an updated event | Change Detector |
| `trending_events` | top forward-looking events by score | Trending Engine |
| `active_providers` | succeeded within `stale_provider_hours`, circuit closed | Provider State Store |
| `stale_providers` | everything else (old / failing / never-run) | Provider State Store |
| `lifecycle_distribution` | count per lifecycle state | Lifecycle Engine |
| `organizer_activity` | top organizers by total/active events | Organizer Intelligence |
| `community_activity` | fastest-growing communities | Community Intelligence |

## Live results (real catalog, 99 events)

**Change detection (proves "continuous"):**
- Run 1: `new = 99` (everything is new the first time).
- Run 2 (no ingestion between): `new = 0, updated = 0, cancelled = 0, expired = 0` — the
  engine correctly detects that nothing changed.

**Lifecycle distribution:** `live_today: 6 · registration_closing: 41 · upcoming: 52`.

**Trending (top 5, score):**
`FutureForge Hackathon 2026 (0.73)` · `HackVSIT7.0 (0.72)` · `FOSS - GCEE (0.71)` ·
`FOSS United Chennai × From Dev to Ops (0.71)` · `Ignisys 1.O (0.71)`.

**Providers:** `active = [cncf, confstech, devfolio, fossunited, gdg, hasgeek, luma]`,
`stale = []` (all had just ingested).

**Organizer profiles (top):**

| Type | Name | Total | Active | Quality | Cities |
|---|---|--:|--:|--:|--:|
| community | Google Developer Groups | 19 | 19 | 0.39 | 17 |
| community | FOSS United | 14 | 14 | 0.42 | 2 |
| community | Hasgeek | 6 | 6 | 0.44 | 1 |
| organization | Google | 3 | 3 | 0.33 | 3 |
| event_series | Build with Gemma | 2 | 2 | 0.50 | 2 |

**Community insights:**
- fastest growing (by forward activity): Google Developer Groups, FOSS United, Hasgeek, CNCF
- most active cities: Bangalore (32), Delhi (15), Mumbai (10), Ahmedabad (2), Bhilai (2)
- recurring series: Build with Gemma
- inactive communities: none (all have upcoming events)

## Reading the numbers honestly

- **`cancelled`/`expired` are 0 in this snapshot** because the two runs are moments apart with
  no source withdrawals or expirations between them — they populate over real time as sources
  change and events end.
- **`stale_providers` is empty** because every provider had just run; it fills as providers go
  quiet or fail (health from the Provider State Store).
- **"fastest growing" is a forward-activity proxy** (most upcoming events), not a true growth
  rate — a real rate needs multiple ingestion snapshots over time.
- **Average quality is modest (~0.4)** because it's mean field-completeness, and most events
  carry only title/date/city (the frozen model's limit) — it rises as providers enrich data.

## Reproduce

```
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.m4d_intelligence
```
