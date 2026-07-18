# Entity Graph

The lightweight knowledge graph: nodes, relationships, traversal. No graph database — a
clean abstraction (`GraphStore`) with an in-memory implementation, built as a rebuildable
projection of the event catalog. Code: `backend/app/entities/`.

## Nodes (entities)

| Type | Source | Notes |
|---|---|---|
| `ORGANIZATION` / `COMPANY` | title keyword-matching | conservative; only known orgs |
| `COMMUNITY` | `provider` + title patterns | strongest signal (GDG, CNCF, FOSS United, Hasgeek) |
| `EVENT_SERIES` | title normalization | year/edition/city stripped |
| `CITY` | `event.city` (already canonical) | clean |
| `VENUE` | `event.location` free-text | sparse |
| `SPEAKER` | — | **empty by design** (no data until Phase 5) |
| `EVENT` | catalog | a lightweight node referencing the event by key (no body) |

Each entity is **canonical** (one node per real-world thing, id-namespaced) and
**accumulates** a profile: `event_keys` (references), `cities`, `categories`, `first_seen`,
`last_seen`, `aliases`, `event_count`.

## Relationships (directed, typed edges)

```
Event ──ORGANIZED_BY──▶ Organization
Event ──HOSTED_BY─────▶ Community
Event ──PART_OF_SERIES▶ EventSeries
Event ──IN_CITY───────▶ City
Event ──AT_VENUE──────▶ Venue
Speaker ─SPEAKS_AT────▶ Event            (empty until Phase 5)
Organization ─HOSTS_SERIES─▶ EventSeries (derived: org organizes an event in the series)
Community ─ACTIVE_IN──▶ City             (derived: a chapter — the community hosts here)
```

## Traversal

`GraphStore` exposes `upsert_entity`, `get_entity`, `entities(type)`, `add_edge`,
`edges(source|target|type)`, `neighbors(id, type, direction)`, `counts()`. Traversal powers
the entity queries and analytics:

- **Events by an organization** → `edges(target="organization:google", type=ORGANIZED_BY)` →
  the source event nodes → strip `event:` → repository keys.
- **A community's chapters** → `neighbors("community:...", ACTIVE_IN, "out")` → city ids.
- **A city's communities** → `neighbors("city:...", ACTIVE_IN, "in")`.
- **A series' editions** → `neighbors("event_series:...", PART_OF_SERIES, "in")`.

Adjacency is indexed by source and target, so a lookup is O(degree), not a scan.

## Query foundation (not wired into SearchService)

`EntityQueries` resolves a name to a canonical entity and traverses to event keys:
`events_by_organization`, `events_by_community`, `events_in_series`, `events_at_venue`,
`events_in_city`, `events_by_speaker` (empty). It returns **event keys** (references into the
Repository), so a caller fetches full events without the graph duplicating event data. Live:
`events_by_community('GDG') → 17`, `events_by_organization('Google') → 3`.

## Analytics

`entity_report(graph)` → entity counts, top organizers, top communities (with chapter
counts), recurring series (≥2 editions), and per-city ecosystems. Live over 102 events:
GDG 17 events / 15 chapters; Bangalore 32 events / 2 communities. "Growth" is approximated
from first/last-seen spans — a true time series needs multiple ingestion snapshots.

## Why it's future-ready

The graph is a **rebuildable projection** behind an interface. Persisting it (SQLite/
Postgres `nodes`+`edges`, later a real graph DB) or enriching extraction (Phase-5 organizer/
speaker fields) changes an *implementation*, never the builder/query/analytics code.
