# Search Query Strategy — D3

How EventScout turns "find new event sources" into a finite, deterministic set of search queries.
The generator (`app/discovery/search/query_builder.py`) is **pure templates — no LLM, no
randomness** — so the same `QuerySpec` always yields the same queries in the same order. That
determinism is what makes discovery reproducible and the frontier's cross-run dedup meaningful.

Companion to **[SEARCH_DISCOVERY_ENGINE.md](SEARCH_DISCOVERY_ENGINE.md)** (the engine + ranking).

## The dimensions

A `QuerySpec` is the cartesian input to discovery — six dimensions, each a tuple:

| Dimension | Purpose | Default (India-tuned) |
|---|---|---|
| `cities` | geographic reach | Bangalore, Delhi, Mumbai, Hyderabad, Pune |
| `technologies` | topical reach (reuses 5A taxonomy vocabulary) | AI, Python, Kubernetes, React, DevOps |
| `platforms` | generic event platforms to `site:`-search | meetup.com, eventbrite.com |
| `community_sites` | known community hosts to enumerate | gdg.community.dev, fossunited.org, hasgeek.com, commudle.com |
| `event_types` | the kind of gathering | meetup, conference, hackathon, workshop |
| `universities` | student chapters / tech clubs | IIT, NIT, BITS Pilani |
| `companies` | corporate dev-events / tech talks | Google, Microsoft, Razorpay |
| `organizations` | explicit named orgs (optional) | — |

Defaults are deliberately modest so the full cross-product stays tractable; a caller widens or
narrows any dimension per run.

## Template families

`build_queries(spec)` emits six ordered families, then de-duplicates (whitespace-collapsed) and
optionally truncates to a `limit`:

**1. Platform site-search** — find groups/events by city × technology on generic platforms:
```
site:meetup.com Bangalore AI
site:eventbrite.com Delhi Kubernetes
```
This is the workhorse for the long tail — one Meetup group per city×topic that no seed list contains.

**2. Community-platform enumeration** — walk a known community host:
```
site:gdg.community.dev India
site:fossunited.org meetup
site:hasgeek.com conference
```
Surfaces individual chapters/events on hosts EventScout already trusts but hasn't fully enumerated.

**3. Topical open-web** — no `site:`, to catch standalone conference/organizer websites:
```
AI conference Bangalore India
React hackathon Delhi India
```
This is how `reactindia.io` / `in.pycon.org`-style independent domains get discovered at all.

**4. University tech clubs** — student chapters and branches:
```
IIT AI club events
NIT Python club events
```

**5. Company developer events** — corporate tech talks / dev meetups:
```
Google tech talks India
Razorpay developer events Bangalore
```

**6. Explicit organizations** — caller-supplied named orgs (`{org} events India`).

## Combinatorics & control

Query count is a product: platform-search alone is `|platforms| × |cities| × |technologies|`, topical
is `|technologies| × |event_types| × |cities|`, and so on. With the spike's spec (2 cities, 4 techs,
1 platform, 3 community sites, 2 event-types, 3 universities, 2 companies) this is **51 unique
queries**. The full default spec is larger; production tiers it rather than running everything each
cycle:

- **De-duplication** is built in — repeated dimension values or overlapping templates collapse to
  one query (whitespace-normalized identity).
- **`limit`** caps the emitted list deterministically (prefix of the stable order).
- **Tiering (future)** — run high-yield families (platform + community) frequently and expensive
  long-tail families (every university × every tech) rarely.

## How queries complement D1/D2

Search queries find **domains**; the crawler inspects them. The division of labor:

```
D3 query  "site:meetup.com Bangalore Python"  ─▶ discovers  meetup.com/bangpypers   (a NEW source)
D1 crawl  meetup.com/bangpypers              ─▶ finds       (feeds? sitemap? JSON-LD?)
D2 crawl  meetup.com/bangpypers              ─▶ finds       __NEXT_DATA__ / embedded events
```

So a query's job is **recall of candidate domains**, not precision about events. A query that
surfaces one genuinely new organizer domain has done its job even if nine other results are noise —
ranking + the threshold filter the noise, and the crawler later decides what's actually ingestible.

## Coverage strategy

- **Geographic**: cities drive both `site:` platform queries and topical queries; India's tier-1/2
  cities are the default spine, extendable to any city list.
- **Topical**: technologies come from the same 5A taxonomy the catalog uses, so discovered sources
  are relevant by construction.
- **Structural**: platforms (Meetup/Eventbrite) + community hosts (GDG/FOSS/Hasgeek/Commudle) target
  the two places most Indian tech events actually live; universities + companies reach the ecosystem
  edges (student chapters, corporate dev-rel) that platform search misses.
- **Precision guardrail**: the ranker's penalty list keeps entertainment/tourism/commerce queries
  (which share city words) from polluting the inbox — see the engine doc.

## Limitations & future work

1. **Static templates, no learning.** Queries don't yet adapt to which templates historically
   yielded ingestible sources. A feedback loop — score each *query* by the crawl-confirmed yield of
   the candidates it produced, then bias generation toward high-yield families — is the natural next
   step (still deterministic: rank queries by past yield, no LLM required).
2. **Hand-curated dimensions.** City/tech/platform/university/company lists are maintained by hand
   and India-tuned. Scaling to new regions or a broader "opportunity" taxonomy (scholarships,
   fellowships) means extending these lists or sourcing them from data.
3. **No query-level dedup against the frontier.** Every run regenerates the full query set; a
   smarter scheduler would skip queries whose entire result set is already known.
4. **Engine-bound recall.** `site:` enumeration is only as complete as the real engine's index of
   that site, and free-tier quotas (~100 queries/day for Google CSE) force query prioritization —
   another reason tiering matters at scale.
5. **LLM-assisted query expansion is explicitly out of scope** for D3 (constraint). Semantic query
   expansion ("events like X"), or reading a discovered page to derive better follow-up queries,
   is D4 territory.

---

**Status:** D3 query strategy is deterministic, template-based, India-tuned, and reproducible.
Paired with the ranking engine it discovers new source domains while filtering off-topic noise.
Learned/adaptive querying is deferred to a later phase.
