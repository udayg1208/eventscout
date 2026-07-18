# Community Graph — Phase 10C

A companion to [ORGANIZER_INTELLIGENCE.md](ORGANIZER_INTELLIGENCE.md), focused on the *graph*: how the
Organizer / Community / Series / Relationship graphs are modelled as one typed graph with views, how
organizers get connected, and how the knowledge graph persists and grows incrementally.

## One graph, four views

Rather than four separate stores, 10C keeps **one `OrganizerGraph`** of typed nodes and typed edges and
exposes the brief's four graphs as filtered views:

- **Organizer Graph** — the whole thing: every organizer + its ecosystem (chapter, university, series,
  sponsors, venue, calendars, feeds, social channels).
- **Community Graph** — `community_view()`: organizer/community/chapter nodes connected by
  `same_community`, `chapter_of`, `belongs_to`, `member_of`, `partner_of`.
- **Series Graph** — `series_view()`: series/recurring nodes + their organizers connected by
  `same_series`, `recurring`, `organizes`, `hosts`.
- **Relationship Graph** — the full edge set (all 13 relation types).

This keeps one source of truth and one incremental writer; a "view" is a cheap subgraph filter.

## Node & edge vocabulary

**Nodes (21):** an organizer is typed precisely — a `chapter` (GDG Bangalore), a `student_chapter`
(GDSC), a `professional_society` (IEEE), a `university_club` (a campus ACM), a `community` (FOSS
United) — and its ecosystem is typed too: `conference_series`, `sponsor`, `venue`, `website`,
`calendar`, `feed`, `github_org`, `discord`, `telegram`, `linkedin_page`, `notion_workspace`,
`university`, `department`.

**Edges (13):** `organizes` / `hosts` (organizer → series / venue), `chapter_of` / `belongs_to` /
`member_of` (organizer → parent / university), `sponsors` (sponsor → organizer), `uses_calendar` /
`uses_feed` / `announces_on` (organizer → its channels), `partner_of` / `same_community` / `same_series`
(organizer ↔ organizer), `recurring` (a series marked recurring).

## How organizers get connected

Two mechanisms build the community structure:

1. **Direct expansion** — `RelationshipDiscoverer` links each organizer to its own ecosystem, and two
   sibling chapters that both declare the same parent (e.g. two GDGs → "Google Developer Group") are
   connected *through that shared parent* via `chapter_of`.
2. **Similarity linking** — `engine.link_similar()` scores every organizer pair on 8 signals (same
   chapter, series, university, city, technologies, venue, sponsors, identity) and adds `same_community`
   / `same_series` edges above a threshold. GDG Bangalore ~`same_community`~ GDG Delhi ~`same_series`~
   (both run DevFest) is exactly this.

## Incremental knowledge graph

The graph grows, it isn't rebuilt. `add_node` merges by canonical id (union of aliases/attributes,
richest label wins, a specific type beats a generic `website`); `add_edge` dedups by
(source, relation, target). Re-ingesting an alias page lands on the *same* node and enriches it. The
`GraphStore` persists nodes and edges as JSON rows (InMemory for a single process, SQLite with
`INSERT OR REPLACE` for durability), so a scheduled re-run adds to the existing graph — `engine.persist()`
/ `load_from_store()` round-trips it.

## Identity is the graph's backbone

Because node ids are canonical identity keys (`org:{sorted distinctive tokens}`), the graph *is* the
identity resolution: every alias of an organizer is the same node by construction, so edges from
different source pages automatically converge. This is why "GDG Bangalore" discovered from its website,
its Discord invite, and a conference announcement all attach to one node.

## Scaling

- **Now:** in-memory + SQLite, single process; `link_similar` is O(n²) over organizers — fine for
  thousands, not millions.
- **Better:** index organizers by chapter/city to limit similarity comparisons to plausible pairs
  (blocking), turning O(n²) into near-linear.
- **Later (seams):** a `GraphDatabaseBackend` (Neo4j/Postgres-graph) for cross-source scale and richer
  traversal queries, and a `SocialChannelFetcher` to enrich channel nodes from public pages (8D rules).
  Both are `NotImplementedError` in 10C.

## Honest self-review (graph view)

- **The four "graphs" are views, not four datasets.** That's a deliberate simplification — it keeps one
  writer and one identity space, but it means the Community/Series graphs are only as rich as the edges
  the engine chose to add; they don't encode relationships the base graph doesn't have.
- **Similarity linking is heuristic and quadratic.** Thresholds are hand-set; a low threshold
  over-connects (everything in a chapter becomes "same community"), a high one under-connects. Blocking
  is described but not implemented.
- **Merging is exact-id, safe but conservative.** Two nodes only merge when their canonical ids match;
  the engine won't fuse near-duplicate ids on its own (no fuzzy node resolution at the graph layer),
  which avoids bad merges at the cost of occasional split identities.
- **Persistence drops field-level provenance.** The store keeps node type/label/attributes/aliases and
  edge reasons, but not each field's full `Provenance` object — the graph structure survives a
  round-trip; the per-field evidence lives on the in-memory `OrganizerProfile`.

---

**Status:** 10C complete — additive, deterministic, byte-level; one typed graph with community/series
views; incremental InMemory + SQLite persistence; 731 tests green; no browser/LLM/network.
**Stopping here — Phase 10D NOT started.**
