# Phase 3F — Entity Architecture (Knowledge Graph Foundation)

EventScout begins to *understand the ecosystem*, not just list events. Organizers,
communities, companies, venues, cities, and series become **canonical, reusable
entities**; events reference them through typed relationships. This is the foundation of
the Event Knowledge Graph.

## The honest premise: this is a projection, not a store

The frozen `Event` model has **no** organizer / speaker / community / venue fields — only
`provider`, `title`, `description`, `city`, `location`. So entities are **derived** from
that data, not read from fields that already exist. The graph is a **rebuildable projection
over the catalog**: run the builder again, get the same graph. It mutates nothing.

Consequences, stated plainly:
- **Communities** derive cleanly from `provider` + title patterns (strong signal).
- **Organizations** derive from conservative title keyword-matching (lossy — only known orgs).
- **Series** derive from title normalization (heuristic).
- **Venues** derive from `location` free-text (sparse).
- **Speakers cannot be derived at all** — no event carries speaker data. The entity type and
  `SPEAKS_AT` relationship exist and are queryable, but are **empty by design** until the
  Phase-5 Opportunity model adds speaker fields and providers populate them. This is not
  faked.

Live result over 102 real events: **4 communities, 3 organizations, 23 cities, 29 venues,
1 recurring series, 0 speakers.**

## Layers (`app/entities/`, reads the frozen Repository, touches no frozen code)

| Module | Role |
|---|---|
| `models.py` | `EntityType`, `EdgeType`, `Entity` (canonical node that *accumulates* profile), `Edge` |
| `graph.py` | `GraphStore` abstraction + `InMemoryGraphStore` (nodes / edges / traversal) — storage-independent, no graph DB |
| `resolution.py` | `EntityResolver` — deterministic matching (normalize → curated aliases → gated fuzzy) |
| `extraction.py` | deterministic derivation of raw entity names from an event |
| `builder.py` | `GraphBuilder` — projects the catalog into the graph (rebuildable, deterministic) |
| `queries.py` | `EntityQueries` — "events by Google / from GDG / in the PyCon series" → event keys |
| `analytics.py` | ecosystem analytics (top organizers/communities, recurring series, city ecosystem) |

## Entity model

Every `Entity` is canonical (one node per real-world thing), namespaced by id
(`community:google-developer-groups`), and **accumulates knowledge** as the graph is built:
`event_keys` (references, never event bodies), `cities`, `categories`, `first_seen`,
`last_seen`, `aliases`, `event_count`. Profiles are read directly off the entity — no
duplication: events reference entities; entities reference events by key.

## Graph model

Directed, typed edges (see [ENTITY_GRAPH.md](ENTITY_GRAPH.md)):
`Event —ORGANIZED_BY→ Organization`, `Event —HOSTED_BY→ Community`,
`Event —PART_OF_SERIES→ Series`, `Event —IN_CITY→ City`, `Event —AT_VENUE→ Venue`,
`Speaker —SPEAKS_AT→ Event`, plus derived `Organization —HOSTS_SERIES→ Series` and
`Community —ACTIVE_IN→ City` (a chapter). Traversal answers the entity queries.

## Storage — clean and independent

Today the graph is **in-memory**, built on demand from the catalog. Because it's behind
`GraphStore` and is a rebuildable projection, persistence is a later choice, not a
requirement: a SQLite (`nodes` / `edges` tables) or Postgres backend implements the same
interface with no change to builders, queries, or analytics. **No graph database** is
introduced. Events are **not** duplicated — the graph holds event *keys*.

## Future expansion

- **Phase 5 (Opportunity model)** adds real organizer/speaker/venue fields; extraction reads
  them instead of parsing titles → the graph gets dramatically richer (speakers populate,
  organizations become reliable) with **no architecture change** — only the extraction step.
- **Persistence**: a `GraphStore` backed by SQLite/Postgres when the graph must survive
  restarts or be queried across instances.
- **Search integration**: `EntityQueries` already returns event keys; wiring "events by
  Google" into `SearchService` is a later step (deliberately not done now).
- **Real graph database** (Neo4j/Neptune) only if multi-hop traversal at scale demands it —
  the abstraction makes it a backend swap, not a rewrite.
