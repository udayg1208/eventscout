# Discovery Optimization — Phase 8A

The layer that continuously improves EventScout's **own discovery engine** — by learning, from
historical outcomes, which queries find good sources, which domains are worth crawling, where
coverage is thin, and which strategy fits each source. It reads what discovery already did
(discovery → onboarding → production outcomes) and produces **recommendations only**. It never
touches the catalog, and it changes nothing automatically.

Code: `backend/app/discovery/optimization/` (new subpackage — additive; no existing discovery file
is modified). No LLM, no Google API, no changes to the Discovery Engine, Onboarding, Production,
Search, Repository, Scheduler, providers, frontend, or API.

## Optimization philosophy

- **Observe, don't guess.** Every recommendation is derived from observed `DiscoveryRecord`s (a
  source + its onboarding/production outcome). Coverage is "what the records contain"; gaps are
  "targets minus covered"; a query's score is "what it actually produced." No speculation.
- **Recommend, don't act.** 8A produces a report. Applying any of it — retiring a query, changing a
  crawl frequency, expanding into a gap — is Phase 8B, behind explicit approval. The only
  components that could *act* (`QueryApplier`, `BudgetEnforcer`, `AdaptiveQueryGenerator`) are
  unimplemented interfaces.
- **Deterministic learning.** "Learning" here is bucketed, weighted arithmetic over history — fully
  explainable, reproducible, and ML-free. Same records → same recommendations.
- **Discovery-only.** It optimizes discovery. It has no path to the catalog, and it doesn't move
  events.

## Pipeline

```
Historical Discovery → Coverage → Gap Analysis → Query Optimization → Budget
                     → Domain Ranking → Strategy Recommendation → Analytics → OptimizationReport
```

```
app/discovery/optimization/
  store.py           DiscoveryRecord (the shared historical unit) + OptimizationStore (report history)
  coverage.py        build_coverage — covered vs uncovered cities/states/tech/communities/universities
  gap_analysis.py    find_gaps — per-city thin-technology gaps (observed-only)
  query_optimizer.py optimize_queries — retire / boost / split / merge / create
  domain_ranker.py   rank_domains — 7-signal DomainTrustScore (explainable)
  budget.py          allocate_budget — increase / maintain / decrease / stop + daily-pool split
  strategy.py        recommend_strategies — best discovery strategy per domain (+ what to avoid)
  analytics.py       build_analytics — yield / efficiency / precision / cost / velocity
  engine.py          OptimizationEngine.run(records) → OptimizationReport
  interfaces.py      future 8B seams (QueryApplier, AdaptiveQueryGenerator, BudgetEnforcer)
```

## Coverage & gap analysis

`build_coverage` compares the distinct cities/states/technologies/communities/universities in the
records against curated India-focused target universes and reports coverage %. `find_gaps` then
detects, per covered city, which technologies are **under-represented relative to that city's own
volume** — the "Bangalore: 120 AI events, 2 Rust events → recommend Rust expansion" pattern.
Observed-only: a city with no records produces no gaps (we never invent demand we haven't seen).

## Query evolution

`optimize_queries` groups history by search query and scores each: good domains (approved/active),
spam (rejected), duplicates, yield. It recommends:

- **retire** — spam-heavy queries, or (from `queries_run`) queries that were executed and found
  nothing.
- **boost** — high-yield queries worth running more.
- **split** — broad queries (many domains) with weak yield.
- **merge** — near-duplicate queries whose result sets heavily overlap (Jaccard ≥ 0.6).
- **create** — new query templates synthesized deterministically from coverage gaps.

## Domain trust & crawl budget

`rank_domains` scores every domain from seven observed signals — approval rate, sandbox quality,
production success, duplicate rate (inverted), freshness, event richness, crawl stability — into an
explainable `DomainTrustScore` (total is exactly the weighted sum of its factors) and a tier
(high/medium/low/dead). `allocate_budget` turns tiers into crawl actions — **increase** high-value
domains (6h), **maintain** medium (12h), **decrease** low (48h), **stop** dead or blacklisted ones —
and distributes a daily crawl pool proportionally to trust.

## Strategy recommendation

`recommend_strategies` looks at which discovery strategy (structured D1 / framework D2 / search D3 /
AI D4) actually produced events for each domain and recommends the **cheapest effective** one, while
flagging wasteful strategies to avoid. This yields exactly the intended guidance: an RSS domain →
`structured`, avoid `[framework, search, ai]` (never run AI on a feed); a Next.js source →
`framework`; a prose source → `ai`.

## Live demonstration (deterministic, recommendations only)

`spikes/p8a_optimization.py` — 11 historical records + 9 queries run:

```
COVERAGE  cities 40% · technologies 12% · communities 25% · universities 0%
GAPS      expand AR/VR / AWS / Azure / Rust search in Bangalore (thin vs 182 events)
QUERIES   boost 'site:meetup.com Bangalore AI' · retire 'free events near me' (spam 1.00)
          retire zero-yield ['site:meetup.com Chennai Go', 'blockchain summit Kolkata']
          merge ['developer meetup india','tech meetup india'] · create from gaps
DOMAINS   gdg.community.dev high 0.985 · … · deadfeed.org dead 0.02
BUDGET    increase 5 top domains (6h) · stop deadfeed.org (dead) + spamB.net (blacklisted)
STRATEGY  gdg→structured avoid[framework,search,ai] · lu.ma→framework · blog→ai
ANALYTICS crawl_efficiency 3.26 ev/attempt · discovery_precision 0.857 · cost_per_discovery 5.4
✔ recommendations only — no discovery/onboarding/production/catalog change
```

## Testing

`tests/test_discovery_optimization.py` — **10 deterministic tests, no network**: coverage
(covered/uncovered), gap analysis (thin-tech flagged, observed-only), query optimizer
(boost/retire/zero-yield/create + merge), domain ranker (tiers + total = Σ factors), production
lowers trust, budget (increase/stop/weights sum to 1), strategy (RSS avoids AI, SPA uses framework),
analytics (precision/efficiency), and the end-to-end engine + persistence. Full backend suite:
**479 tests**.

## Scaling to 100,000 sources

- **Every stage is a linear pass or a group-by over records** — coverage, ranking, budget, analytics
  are all O(records); query-merge is the only pairwise step and operates on distinct queries, not
  sources (far fewer).
- **The store is append-only report history** (SQLite → Postgres unchanged), so optimization runs
  are cheap snapshots over a windowed slice of history.
- **Budget is the scaling lever** — at 100k domains you cannot crawl them all every cycle; the
  trust-proportional daily pool is exactly the mechanism that concentrates a fixed crawl budget on
  the domains that earn it and stops the dead weight.
- **Query evolution bounds search cost** — retiring zero-yield/spam queries and merging duplicates
  keeps the query set (the expensive part of search discovery) small and high-yield as it grows.
- **Coverage/gaps direct expansion** — instead of blind breadth, the system expands where observed
  data shows thin coverage, so growth stays efficient at scale.

## Honest self-review

**Truly true**
- Every output is observed-data-derived and explainable (trust total = Σ factors; gaps cite
  observed counts; query scores cite yields). Nothing is applied — the acting seams are
  unimplemented.

**Weaknesses / deferred**
1. **Single-snapshot, no trend.** 8A optimizes over one batch of history; coverage/velocity "trend"
   needs comparison across runs (the store keeps history, but the engine doesn't diff yet).
2. **Target universes are curated and finite.** Coverage % is measured against hand-listed
   cities/technologies/communities; a real deployment would source these from data, and "100%
   coverage" only means "of the curated targets."
3. **Trust defaults are neutral, not punitive.** Absent signals (no duplicate data, no production
   run) score neutrally, so a rejected-but-not-blacklisted domain can still land in "low/decrease"
   rather than "stop." Rejection alone doesn't zero the budget unless the domain is dead or
   blacklisted.
4. **Gap thresholds are heuristic.** The min-city-volume and thin-ratio constants are reasoned, not
   tuned; a very small city can be flagged noisy or a large one under-flagged.
5. **`create` queries are template-based, not adaptive.** New queries come from a fixed
   `site:meetup.com {city} {tech}` template; genuinely novel query generation is the deferred
   `AdaptiveQueryGenerator` (8B).
6. **Small-sample domain scores are volatile.** A domain with one record gets a full trust score
   from that single observation; confidence-weighting by record count is future work.

## Where Phase 8B begins (NOT this phase)

8A tells discovery how to improve; it does not act. Phase 8B would *apply* the recommendations —
real search-engine integration to run the boosted/created queries, adaptive query generation beyond
templates, and pushing budgets into the real crawl scheduler — i.e. autonomous web expansion. That
crosses from "recommend" to "act" and requires explicit approval.

---

**Status:** 8A complete. Additive; discovery/onboarding/production/catalog untouched; 479 tests
green; deterministic, explainable, observed-data-only, recommendations-only. **Stopping here —
Phase 8B NOT started.**
