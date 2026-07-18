# Discovery Graph — Phase 8C

The persistent graph EventScout grows from the web: every discovered object is a node, every
relationship an edge. Companion to **[WEB_EXPANSION_ENGINE.md](WEB_EXPANSION_ENGINE.md)** (the engine
that builds it).

## Why a graph

A flat inbox of URLs loses structure: it can't say "this domain *owns* these pages", "this page
*contains* this feed", "this organizer *hosts* this chapter". The Discovery Graph keeps those
relationships, so downstream phases can traverse — "give me every feed under this organizer", "which
communities reference this GitHub org" — and so re-discovery **merges into** existing knowledge
rather than piling up duplicates.

## Node types (16)

| Category | Nodes |
|---|---|
| structure | `PAGE`, `DOMAIN` |
| feeds/data | `RSS`, `ICS`, `JSONLD`, `SITEMAP`, `CALENDAR` |
| sources | `BLOG`, `COMMUNITY`, `ORGANIZER` |
| platforms | `GITHUB`, `NOTION`, `DISCORD`, `TELEGRAM` |
| entities | `UNIVERSITY`, `COMPANY` |

`SOURCE_NODES` marks the leaf types worth a Discovery Inbox candidate (feeds, calendars, JSON-LD,
communities, organizers, and the platform/blog nodes) — as opposed to navigational `PAGE`/`DOMAIN`.

## Edge types (8)

| Edge | Meaning |
|---|---|
| `links_to` | page → page (an in-scope hyperlink, queued for crawl) |
| `owns` | domain → page (a page belongs to its domain) |
| `hosts` | reserved: platform → hosted entity |
| `references` | page → external domain / platform node (reached, not crawled) |
| `belongs_to` | reserved: chapter → organizer |
| `contains_feed` | page → RSS/Atom feed |
| `contains_calendar` | page → ICS / Google Calendar |
| `contains_events` | page → JSON-LD / event-bearing structure |

## Node identity & deduplication

A node's key is its **canonical form**, so the same thing never becomes two nodes:

- **URLs** are canonicalized (`dedup.canonicalize`): normalized (D1's `normalize_url`), tracking
  params stripped (`utm_*`, `gclid`, `fbclid`, …), and an explicit `<link rel=canonical>` or a
  redirect target preferred over the raw URL.
- **Keys**: a `DOMAIN` node keys by its registrable domain (`domain#community.dev`); everything else
  keys by `type#canonical-url` (`rss#https://gdg.org/feed.xml`). So a feed found on three pages, a
  page reached via a tracking link, and its canonical are all **one** node.

`upsert_node` merges on key collision (fills a missing title, updates `last_seen`, unions `attrs`) and
returns whether it was newly added; `add_edge` dedups on `(source, target, type)`. Re-discovery
therefore enriches the graph without inflating it — in the demo, a second full crawl added **0**
nodes.

## How the graph is built (per page)

```
crawl page P (canonical url, domain D)
  ├─ upsert PAGE(P), DOMAIN(D)            + edge  D --owns--> P
  ├─ detect_feeds(P)  [reused D1]         → RSS/ICS/JSONLD nodes  + contains_feed/calendar/events
  ├─ <link rel=alternate> feeds          → RSS nodes             + contains_feed
  ├─ .ics / Google-Calendar links        → CALENDAR nodes        + contains_calendar
  ├─ github / notion / discord / telegram / blog links → typed nodes + references
  └─ for each in-scope anchor L:
        upsert PAGE(L)  + edge  P --links_to--> L   ; enqueue L (by priority)
     for each out-of-scope anchor L:
        upsert DOMAIN(reg(L))  + edge  P --references--> DOMAIN   (reached, not crawled)
```

Every leaf source node also produces a Discovery Inbox candidate (`discovered_by="expansion"`, the
node type recorded in the candidate's `classification` field, `status=NEW`). The rich node typing
lives in the additive graph; the inbox candidate uses an existing `FeedType` (feeds → RSS/ICS/JSON-LD,
everything else → `SEARCH_RESULT`), so the frozen Discovery models are untouched.

## Querying the graph

`ExpansionGraph` exposes `get(key)`, `nodes()`, `edges()`, `nodes_of(type)`, `neighbors(key,
edge_type=…)`, and `stats()` (counts by node/edge type). Example traversals a later phase can build
on: "all `contains_feed` neighbors of an organizer's pages", "every `DOMAIN` a community
`references`", "all `GITHUB` nodes reachable from a seed".

## Persistence & growth

`ExpansionStore` (InMemory + SQLite) snapshots the graph (`save_graph`) and rebuilds it
(`load_graph`), so the graph **survives runs and grows incrementally** — each expansion adds to the
prior graph rather than starting over. Nodes and edges are upserted (idempotent), and the store is
append/replace only — nothing is destroyed. In the demo the graph reloaded identically (28 nodes /
33 edges) after persistence.

## Growth characteristics

- **Sub-linear in fetches.** The same domains, feeds, and platforms recur across pages, so nodes
  grow much slower than pages crawled, and re-crawls add ≈0.
- **Bounded by scope + budget.** Blocked hosts never become `PAGE` nodes (only, at most, a single
  `DOMAIN` reference node); per-domain budgets cap how many pages a domain contributes.
- **Dedup is the scaling primitive.** Because identity is canonical, the graph is naturally a *set*
  of real things — the mechanism that keeps it finite as crawling scales.

## Honest limitations

- **`DOMAIN` reference nodes inflate the domain count** — every out-of-scope link adds one, so the
  domain tally includes places deliberately not crawled.
- **No pruning/retention yet** — the graph only grows; a long crawl needs an aging policy.
- **HTML-only edges** — `links_to` reflects served anchors, so client-rendered navigation (SPAs) is
  under-represented (see the engine doc's self-review).
- **`hosts` / `belongs_to` are reserved** — declared for the full model but not yet emitted; they
  await organizer/chapter resolution (a future enrichment).

---

**Status:** a deduplicated, typed, persistent graph of everything discovery finds on the web —
16 node types, 8 edge types, canonical-key identity, incremental growth. The structure downstream
phases traverse; the mechanism that keeps web-scale discovery finite.
