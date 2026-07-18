# Web Expansion Engine — Phase 8C

The autonomous web-expansion layer. Instead of stopping after discovering a single page, EventScout
now **crawls every discovered page and grows a persistent Discovery Graph** from it — new domains,
event pages, RSS/Atom feeds, ICS/Google calendars, JSON-LD, GitHub/GitLab orgs, Notion sites,
Discord invites, Telegram channels, blogs, community and chapter pages. Every discovered source
becomes a Discovery Inbox candidate (`discovered_by="expansion"`, `status=NEW`). Output stops at the
Discovery Inbox — nothing is onboarded or promoted.

Code: `backend/app/discovery/expansion/` (new subpackage — additive). It **reuses** D1's fetcher,
robots, link/feed extractors, feed detection, and candidate builder; it modifies none of them, nor
Search, the Repository, D1–D4, Web Discovery (8B), providers, the scheduler, Production, the
Catalog, the frontend, or the API. HTML only — no browser, no Playwright/Selenium, no LLM.

## Architecture

```
Discovery Inbox → Expansion Queue (frontier) → Fetch (robots + budget + checkpoint)
   → Extract (links + feeds + calendars + communities + GitHub/Notion/Discord/Telegram/blogs)
   → Graph (dedupe nodes/edges) → Priority → Frontier … → Discovery Inbox
```

```
app/discovery/expansion/
  models.py       NodeType (16) · EdgeType (8) · GraphNode/GraphEdge · ExpansionPriority · budgets
  graph.py        ExpansionGraph — dedup nodes by key, edges by (src,tgt,type), neighbors, stats
  extractor.py    extract(page) — reuses D1 link/feed extractors + platform/calendar/blog regexes
  scope.py        evaluate_scope — same-domain / trusted-external / blocked / depth / out-of-scope
  priority.py     score_url — explainable ExpansionPriority (feed/calendar/events/meetup/… signals)
  budget.py       BudgetTracker — per-domain max pages/depth/failures/cooldown/bandwidth → stop
  frontier.py     ExpansionFrontier — pending/visited/failed/blocked/deferred, priority-ordered
  dedup.py        canonicalize (tracking/canonical/redirect) + node_key
  checkpoint.py   CheckpointStore (InMemory + SQLite) — incremental crawling (last_crawl, ETag)
  crawler.py      ExpansionCrawler — polite fetch (robots + budget + checkpoint), content fingerprint
  store.py        ExpansionStore (InMemory + SQLite) — persist + reload the graph, report history
  engine.py       ExpansionEngine.expand(seeds) → ExpansionReport
  interfaces.py   future seams: RenderedExtractor (SPA), SocialExpander (8D)
```

## Crawl strategy & scope rules (recursion control)

The crawler never runs forever. Every candidate link passes the **Scope Engine** before it can be
queued:

- **ALLOW** — same registrable domain as a seed.
- **CROSS_TRUSTED** — a curated event/community platform (Meetup, GDG community.dev, FOSS United,
  Hasgeek, Lu.ma, Eventbrite, …) may be crossed one hop.
- **BLOCK** — social/aggregator/commerce hosts (Facebook, Twitter/X, LinkedIn, YouTube, Amazon, …)
  that would explode the frontier are refused.
- **DEPTH_EXCEEDED** — beyond `max_depth` (default 2).
- **OUT_OF_SCOPE** — recorded as a `DOMAIN` reference node (the graph reaches out) but not crawled.

Recursion is further bounded by the **Priority Engine** (crawl high-value links first — feeds,
calendars, "events"/"meetup"/"chapter"/"community" URLs, trusted domains, high domain-trust — every
score explainable) and the **Crawl Budget** (per-domain max pages/depth/failures, a post-failure
cooldown, a daily page limit, and a bandwidth ceiling; a domain that trips any ceiling is *stopped*
for the run). A per-page link cap (120) stops one page from flooding the queue.

## Graph growth

Every crawled page adds a `PAGE` node and a `DOMAIN` node (`owns` edge); every discovered feed/
calendar/JSON-LD adds a typed node with a `contains_feed`/`contains_calendar`/`contains_events`
edge; every platform link (GitHub/Notion/Discord/Telegram/blog) adds a typed node with a
`references` edge; every in-scope link adds a `PAGE` node + `links_to` edge (and is queued). Nodes
dedup by canonical key, edges by `(source, target, type)` — re-discovery **merges**, never
duplicates. Full model in **[DISCOVERY_GRAPH.md](DISCOVERY_GRAPH.md)**.

## Incremental crawling

The `CheckpointStore` records `last_crawl` + a content fingerprint (a lightweight ETag) per URL. A
second run skips URLs crawled within the refresh window (24h) — so re-expansion is cheap and the
graph grows incrementally rather than re-fetching everything. (Header ETag/Last-Modified conditional
GETs are a small add once the fetcher surfaces headers — the schema is already there.)

## Safety

Reuses D1's robots machinery (per-origin `RobotsCache`, honoring `Disallow`/`Crawl-delay`) and adds
per-domain rate spacing, exponential-backoff-free polite fetch (the D1 fetcher already times out),
canonical-URL dedup, scope blocking, a depth limit, and per-domain budgets. It never behaves like an
abusive crawler: bounded pages, bounded depth, bounded bandwidth, robots-respecting, and it stops
low-value domains automatically.

## Live demonstration (deterministic mock site)

`spikes/p8c_expansion.py` (StaticFetcher — swap in `HttpxFetcher` for the real web) seeds one
organizer page and expands:

```
SEED https://gdg.org/
CRAWL   pages fetched=6  (home + events + community + 2 chapters + a cross into meetup.com)
        frontier: visited 6 · blocked 1 (facebook) · failed 0     checkpoints=7
SOURCES feeds=5 · calendars=1 · github=2 · notion=1 · discord=1 · telegram=2 · blogs=1
GRAPH   28 nodes / 33 edges
        nodes: page 6 · domain 9 · rss 2 · jsonld 3 · github 2 · telegram 2 · calendar/notion/discord/blog 1
        edges: references 16 · owns 6 · links_to 5 · contains_events 3 · contains_feed 2 · contains_calendar 1
INBOX   11 candidates (all discovered_by=expansion, status=NEW)
RUN 2   pages fetched=0  skipped=1  → incremental (checkpoints) ; graph reloaded 28 nodes / 33 edges
✔ stops at the Discovery Inbox — no onboarding, no promotion, no catalog write
```

From a single seed page it discovered 11 new sources across 9 domains, built a 28-node graph, and
the second run correctly did nothing (everything crawled recently).

## Testing

`tests/test_expansion.py` — **11 deterministic tests, no network (StaticFetcher + fixtures)**: graph
dedup (nodes + edges), frontier priority order + dedup, canonicalization (tracking/canonical/
redirect), scope decisions (allow/cross/block/depth/out-of-scope), checkpoint (InMemory + SQLite),
priority (explainable, feeds rank high), budget (page/failure/cooldown caps), extraction (all source
types + canonical), and the engine end-to-end (graph grows, inbox updated, incremental second run
skips + persists, budget stops a domain). Full backend suite: **503 tests**.

## Scaling to millions of pages

- **Node/edge dedup is O(1) set/dict membership** — the graph grows sub-linearly in fetches because
  the same feeds/domains recur; the demo's 6 pages produced 28 nodes, but re-crawls add ~0.
- **Budget + scope are the governors** — per-domain page/bandwidth ceilings and the trusted-external
  allowlist keep the frontier from exploding combinatorially; blocked hosts are refused up front.
- **Incremental checkpoints** mean steady-state cost is "crawl only what changed", not "re-crawl the
  web" — essential at millions of pages.
- **Storage is the existing storage-agnostic pattern** (SQLite → Postgres unchanged); the graph and
  checkpoints are both append/upsert, index-friendly, and the graph can be sharded by domain.
- **Priority focuses the budget** — with a fixed crawl budget the highest-value links (feeds,
  calendars, event/community pages) are visited first, so coverage-per-crawl stays high as scale
  grows.

## Honest self-review

**Truly true**
- Every discovered source traces to a real anchor/feed in the HTML; the graph dedups; scope/budget/
  robots/depth are all enforced; the incremental second run provably does nothing.

**HTML-only & SPA limitations**
1. **HTML only — SPAs are largely invisible.** A React/Vue/Next.js page that builds its links and
   event data client-side exposes little in raw HTML, so expansion under-discovers on modern JS
   sites (the same blind spot D2 addresses for *event data*, but here for *links*). D2's hydration
   extraction is reused for JSON-LD, but client-rendered *navigation* is not followed. The
   `RenderedExtractor` seam (still no browser in 8C) is where a future renderer plugs in.
2. **No browser rendering — by design.** No Playwright/Selenium; a page that needs JS execution to
   reveal its links yields only what's in the served bytes.

**Graph explosion & budget tradeoffs**
3. **Graph explosion is a real risk** if scope/budget are loose. The mitigations (blocklist,
   trusted-external allowlist, depth limit, per-domain budgets, per-page link cap) are heuristic
   constants, not adaptive — a hub page on an in-scope domain can still fan out widely within
   budget. Tighter budgets reduce coverage; looser budgets risk runaway crawls. There is no global
   (cross-domain) page cap yet, only per-domain.
4. **Priority/scope lists are curated and finite** — the trusted-external and blocked sets are
   hand-maintained; a legitimate new platform isn't crossed until it's added, and a new noise host
   isn't blocked until it's listed.

**Storage & correctness**
5. **Storage grows with the graph.** Nodes/edges accumulate; without pruning, a long-running crawl's
   graph grows unbounded (dedup slows it, but doesn't cap it). A retention/aging policy is future
   work.
6. **Incremental is time-based, not content-based.** Skipping is by `last_crawl` window; true
   conditional GETs (ETag/If-Modified-Since) await header support in the fetcher. The content
   fingerprint is stored but not yet used to short-circuit unchanged pages.
7. **Reference nodes can inflate the domain count** — every out-of-scope link creates a `DOMAIN`
   node, so the graph's domain count includes places we deliberately didn't crawl.

## Where Phase 8D begins (NOT this phase)

8C expands over the open web via HTML. Phase 8D — **Public Social Discovery** — would enrich the
Discord/Telegram/GitHub nodes via their public APIs (members, pinned events, org repos), and add
browser-rendered expansion for SPAs. Both are larger grants of reach and require explicit approval.

---

**Status:** 8C complete. Additive; D1–D4 / 8B / frozen systems untouched; 503 tests green; HTML-only,
polite (robots + budget + scope + depth), incremental, and discovery-only. **Stopping here — Phase
8D NOT started.**
