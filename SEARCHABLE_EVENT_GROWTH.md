# Searchable Event Growth — Phase 11A

The single success metric: **active searchable events in `catalog.db`** (what the API/search serves).

## Headline

```
   BEFORE  ████████████████                                 168
   AFTER   ████████████████████████████████████████████████ 505     (+337, 3.0×)
   TARGET  ████████████████████████████████████████████████████████████████████████████████████████████ 1000
```

**168 → 505 measured active searchable events.** Target 1,000 not reached; discovery yield collapsed to
0 new / ~200 pages across 5 consecutive runs (measured exhaustion of the reachable event pool).

## Growth curve (measured)

```
events
 505 |                                   ●━━━━●━━━━●━━━━●━━━━●   ← exhaustion: +0, +0, +0, +0, +0
 501 |                              ●━━━━┛
     |                             ╱
 419 |                    ●━━━━━━━━┛
     |                   ╱  (Unstop broadened +82)
     |                  ╱
     |          (Unstop +213)
 206 |     ●━━━━┛
 168 |●━━━━┛ (existing providers refresh +38)
     +----+----+--------+--------+----+----+----+----+----+---
      base  r2   r3       r4      r5   r6   r7   r8   r9  r10
```

| Stage | Active | Cumulative growth |
|---|---:|---:|
| Baseline | 168 | — |
| Refresh existing 30 providers | 206 | +38 (+23%) |
| Add Unstop (open) | 419 | +251 (+149%) |
| Broaden Unstop (full upcoming) | 501 | +333 (+198%) |
| Add 3 Meetup ICS feeds | **505** | **+337 (+201%)** |
| 5× exhaustion re-crawl | 505 | +337 (flat) |

## What drove the growth

- **Unstop: +295 events (58% of the final catalog)** — one new provider on the existing
  `EventProvider` interface. This is essentially the entire campaign.
- Existing providers refresh: +38.
- New Meetup ICS feeds: +4.

## Composition of the growth (the +337 new events)

- **251 hackathons** (was ~40) — the category that grew most, almost entirely Unstop.
- **64 workshops · 29 conferences · 27 AI events** — new via Unstop.
- **84 university-hosted** — the Tier 1 ecosystem, surfaced via Unstop.
- Mode shifted toward hackathons/online: 215 online / 290 offline.

## Distance to target

- Reached **505 / 1000 = 50.5%** of target.
- Remaining **495** events are **not present in any machine-readable, upcoming-India source** reachable
  by a no-browser/no-auth system (measured — see [CATALOG_EXPANSION_REPORT.md](CATALOG_EXPANSION_REPORT.md)
  gap table). The catalog now grows automatically as new events are published to the platforms the
  pipeline already reads — no further code required.

---
Measured from `backend/catalog.db`. Real events only; no synthetic data. **505 searchable events.**
