# Event Discovery Engine — a self-growing discovery architecture

Pure research + architecture. No code. The goal: stop depending on engineers manually finding
providers, and instead let EventScout **discover events that nobody explicitly added**.

## First principles — the bottleneck was misdiagnosed

Every prior phase proved the same thing: **ingestion mechanisms are solved** (ICS/RSS/JSON-LD/
Bevy/JSON all parse at ₹0). What blocked scale was **discovery** — finding the source URLs. I
concluded several ecosystems were "inaccessible at ₹0" (Meetup groups, IEEE ~1000 branches,
university clubs). 

**That conclusion was wrong in an important way, and this is the key insight of this design:**
those sources have no *enumerable API*, but **they are all indexed by search engines**. A query
like `site:meetup.com bengaluru python`, `site:vtools.ieee.org india`, or
`site:*.community.dev` returns exactly the URLs my manual guessing (~40% hit rate) could not
find. The pages I called "undiscoverable" are one search query away. **Discovery is automatable
— I was using the wrong tool (guessing + direct APIs) instead of the right one (the web's own
index + crawling + AI extraction).**

So the reframe:

| Old model (manual) | New model (Discovery Engine) |
|---|---|
| Engineer finds a source → writes a provider | Engine finds sources → auto-registers them as data |
| Ceiling = human curation throughput (~20 providers) | Ceiling = what exists × discoverable × ingestible × quality |
| ~250–400 concurrent (measured) | long-tail unlocked → materially higher |
| Linear maintenance (add providers forever) | Tune one engine; catalog self-expands |

The Provider Registry stops being **code** and becomes **a table the engine writes**.

## The seven discovery strategies (analyzed)

Scoring: Automation (how fully it runs without humans) · Complexity (build effort) · Yield
(events surfaced) · FP (false-positive rate) · Maint (ongoing upkeep). "Implement?" is my
honest recommendation.

### 1. Seed-based web discovery
- **How:** start from known organizers (we already hold them in the Phase-3F Entity Graph),
  crawl their pages, follow outbound links, detect new event pages/organizers, recurse.
- **Legal/ethical:** ✅ crawling public pages is fine **if** robots.txt + polite rate limits are
  respected and no auth/anti-bot is bypassed.
- **Automation:** High · **Complexity:** Med (crawler + politeness + frontier) · **Yield:** Med
  (tech-event sites cross-link: series, sponsors, partners) · **FP:** Med-High (most links
  aren't events → needs the feed-detector + AI gate) · **Maint:** Med.
- **Implement? YES** — the backbone of the engine.

### 2. Organization discovery
- **How:** discover new communities/organizers/meetup-groups/clubs from public references
  (mentions on other pages, GitHub, social bios, sponsor lists), resolve them to canonical
  entities (reuse the 3F resolver), then probe each for an event feed.
- **Legal:** ✅ public references. **Automation:** Med-High · **Complexity:** Med (entity
  resolution, already built) · **Yield:** Med · **FP:** Med · **Maint:** Med.
- **Implement? YES** — feeds the Entity Graph, which becomes the discovery substrate.

### 3. Search-engine discovery ⭐ (the unlock)
- **How:** templated queries against a search API →
  `site:meetup.com <city> <topic>`, `<tech> conference india 2026 register`,
  `site:*.community.dev`, `"tech fest" site:.edu.in`, `devfest <city> 2026`,
  `site:lu.ma india <topic>`. Parse result URLs → hand to the feed-detector/AI-extractor.
- **Legal/ethical:** ✅ **via an official API** (Google Programmable Search — 100 free
  queries/day; or a self-hosted SearXNG meta-search). ❌ **scraping Google/Bing SERPs directly
  violates their ToS** — do not do that. This is the one strategy with a real cost/quota wall.
- **Automation:** High · **Complexity:** Med · **Yield:** **High** (the index already contains
  every Meetup group, IEEE branch, college club, conference site) · **FP:** Med · **Maint:** Med
  (query tuning + quota management).
- **Implement? YES** — this is what dissolves the discovery ceiling I hit. It reaches the
  long-tail (Meetup/university/community) that direct APIs and guessing could not.

### 4. Structured-web detection (adapter auto-selection)
- **How:** given any discovered domain, auto-detect *how to ingest it*: check `robots.txt` for
  sitemap/feed hints, `<link rel=alternate>` for RSS/Atom/ICS, `/sitemap.xml`, JSON-LD `Event`
  in HTML, embedded `__NEXT_DATA__`, `/events` + `/calendar.ics`. Output a typed adapter spec
  (family = json-ld | rss | ics | sitemap | bevy | next-data | ai-extract).
- **Legal:** ✅ structured data is published *to be consumed*. **Automation:** High ·
  **Complexity:** Med · **Yield:** High (converts a domain → an ingestible feed) · **FP:** **Low**
  (structured Event data is high-confidence) · **Maint:** Low.
- **Implement? YES** — the bridge from "a URL" to "a registered provider."

### 5. Link-graph expansion
- **How:** exploit the semantic graph we already build. Event → Organizer → Website → their
  other events; Sponsors → sponsor event pages; Speaker → their talks/other events; Chapter →
  sibling chapters; Series → past/future editions. Each hop yields new seeds.
- **Legal:** ✅. **Automation:** High · **Complexity:** Med-High (graph traversal + resolution,
  partly built in 3F) · **Yield:** Med-High (the ecosystem is densely interlinked) · **FP:** Med
  · **Maint:** Med.
- **Implement? YES** — turns the Entity Graph from a read-model into a *discovery engine input*.

### 6. AI-assisted discovery
- **How:** use an LLM (we already run Gemini Flash-Lite) for four jobs a crawler can't: (a)
  **classify** "is this a professional-tech event source (not entertainment/edtech-spam)?"; (b)
  **extract** events from *unstructured* HTML that has no JSON-LD (the university/Instagram-style
  pages) — title, date, city, mode; (c) **cluster** discovered organizers to name whole
  ecosystems ("these 40 are GDG chapters", "these are IEEE branches") and spot gaps; (d)
  **generate** the next batch of search queries.
- **Legal/ethical:** ✅ running our own model on public content. **Grounding is mandatory** — the
  LLM's output is a *hypothesis*, validated against the real page (URL resolves, date parses,
  not a dup) before it enters the catalog. Never store an LLM claim as a fact ungrounded.
- **Automation:** High · **Complexity:** Med (orchestration, prompt/version control, cost caps)
  · **Yield:** **High** (unlocks the no-structured-feed long tail) · **FP:** Med (hallucination
  → mitigated by grounding + a confidence gate) · **Maint:** Med (prompt/model drift).
- **Implement? YES, selectively** — as classifier + extractor + query-generator, always behind
  validation. This is what makes the "no feed" sources (university clubs) finally reachable.

### 7. Continuous ecosystem expansion (the meta-loop)
- **How:** a feedback loop — every validated source's outbound links + extracted organizers
  become new seeds; search + clustering surface adjacent ecosystems; dead sources are pruned;
  health/quality scores steer crawl budget. The catalog grows itself.
- **Implement? YES** — this is the whole point; strategies 1–6 are its stages.

**Rejected as primary strategies (but usable):** raw SERP scraping (ToS), social-media scraping
(Instagram/WhatsApp — anti-bot + ToS + privacy), and anything requiring auth/anti-bot bypass —
these stay **out of bounds** on the same principle held throughout the project.

## Architecture — the Event Discovery Engine

Sits **before** the Provider layer, exactly as proposed:

```
                         ┌──────────────── EVENT DISCOVERY ENGINE ────────────────┐
  Seeds:                 │                                                        │
  • Entity Graph (3F)    │   ┌──────────┐   ┌─────────┐   ┌──────────────┐        │
  • search-query templates│  │ FRONTIER │─▶│ CRAWLER  │─▶│ FEED DETECTOR │        │
  • human-added seeds    │   │ (queue,  │   │ (polite, │   │ (JSON-LD/RSS/│        │
                         │   │ politeness)│  │ robots)  │   │ ICS/sitemap) │        │
                         │   └────▲─────┘   └─────────┘   └──────┬───────┘        │
                         │        │                              ▼                │
                         │   ┌────┴──────┐   ┌──────────────┐  ┌──────────────┐   │
                         │   │ FEEDBACK  │◀─│  VALIDATOR &  │◀─│ AI CLASSIFIER│   │
                         │   │ (new seeds,│  │  SCORER      │  │ + EXTRACTOR  │   │
                         │   │  pruning) │   │ (India? tech?│  │ (Gemini)     │   │
                         │   └───────────┘   │  quality? dup?)│ └──────────────┘   │
                         │                   └──────┬───────┘                     │
                         └──────────────────────────┼─────────────────────────────┘
                                                    ▼  (auto-registers a typed source)
                        PROVIDER REGISTRY  ── now DATA the engine writes, not code ──
                                                    ▼
                     INGESTION → NORMALIZATION → AI (enrich/classify) → CATALOG
```

### Components
1. **Frontier & Seed Manager** — priority queue of candidate URLs/queries; per-domain politeness
   (robots.txt, rate limit, crawl-delay); seeds from the Entity Graph, query templates, and a
   human "seed inbox."
2. **Crawler** — polite, cached fetcher; obeys robots.txt; never bypasses auth/anti-bot; backs
   off on 429/403.
3. **Feed Detector** — classifies a page/domain into an *adapter type* (json-ld / rss / ics /
   sitemap / bevy / next-data / ai-extract) — high-confidence, structure-based.
4. **AI Classifier + Extractor** — Gemini: is-this-a-quality-tech-source? extract-events-from-
   unstructured-HTML; cluster organizers; generate next queries. Always grounded.
5. **Validator & Scorer** — the **quality gate**: India? professional-tech (not entertainment)?
   not a duplicate of an existing source/event (reuse the dedup + entity resolver)? Assign
   quality/maintenance/priority; decide auto-register vs. human-review.
6. **Feedback Loop** — successful sources → new seeds (outbound links, extracted organizers,
   sibling chapters); dead sources pruned; scores steer budget.
7. **Auto-populated Provider Registry** — discovered+validated sources become **rows** (type,
   url, city, cadence, scores). The generic adapters (today's `ICSProvider`; future
   `RSSProvider`/`JSONLDProvider`/`AIExtractProvider`) ingest them. **A new source = a row the
   engine wrote, not a class an engineer wrote.**

### Design principles (non-negotiable)
- **Human-in-the-loop quality gate:** above a confidence threshold → auto-register; below →
  a one-click "provider inbox" for approval. Protects the quality bar while staying mostly hands-off.
- **Grounding over trust:** every AI-extracted event is validated (URL resolves, date parses,
  city normalizes, not a dup) before catalog entry.
- **Legality by construction:** official APIs/feeds, robots.txt respected, no anti-bot/auth
  bypass, identifiable user-agent, conservative rate limits.
- **Reuse, don't rebuild:** the engine feeds the *existing* Provider Registry → Ingestion →
  dedup → Entity Graph (3F) → enrichment (5A) → Catalog. It changes *how sources arrive*, not
  the downstream pipeline (which is frozen and proven).
- **Dedup is load-bearing:** at organizer level (entity resolver, 3F) and event level (existing
  dedup, Phase-2 #3). Automated discovery multiplies duplicate risk — the deduper is what keeps
  quality high.

## Honest 5-year ceiling (with this engine)

Two numbers behave very differently. **Concurrent** is fundamentally capped by *how many events
are scheduled at any instant* (the thin-forward-pipeline law I measured: most communities
haven't posted their next event). **Searchable-over-time** is capped by *production rate ×
discoverable-fraction* — and that is where the long tail compounds.

| Metric | Manual model (today) | Discovery Engine, mature (5-yr) | Confidence |
|---|---|---|---|
| **Auto-discovered sources/providers** | ~20 | **1,000–5,000** (most low-yield, auto-managed) | Med |
| **Organizers tracked** (entity graph) | ~30 | **5,000–20,000** | Med |
| **Searchable events / rolling year** | ~1,000–1,500 | **10,000–40,000** | Low-Med |
| **Concurrent upcoming** | ~250–400 | **800–2,500** (peak season top of range) | Med |

**Reasoning (Fermi, honest):** India plausibly has a few thousand semi-active tech-event
producers (GDG ~200, IEEE ~1,000 branches, ~5,000+ college clubs, ~500 Meetup groups,
conferences, hackathons, company/community calendars). At ~5–15 events/producer/year and a
**discoverable-and-quality-passing fraction of ~20–40%**, the annual searchable pool is
plausibly **10k–40k**. Concurrent stays far lower because scheduling is sporadic + seasonal,
but the long tail (thousands of producers each occasionally scheduling) lifts the concurrent
baseline several-fold over the ~400 manual ceiling.

**So the honest answer to the hypothesis (1,000–5,000 searchable):** with a Discovery Engine,
**not only achievable but a floor** — the realistic 5-year searchable ceiling is **~10k–40k/year**,
and even **concurrent** plausibly reaches **~1,000–2,500** at peak. The manual ceiling I reported
(~400 concurrent) was real *for the manual model*; **the Discovery Engine is precisely what breaks
it.** My earlier pessimism was a property of the *method*, not of the *ecosystem*.

**What it costs (the caveats that keep it honest):**
- No longer strictly ₹0 at full scale: a search API quota (Google free tier caps at 100/day →
  paid beyond) and LLM tokens (Gemini free tier limited) become the new constraints. Both are
  *cheap*, not free — the constraint shifts from human labor to modest API spend.
- **Quality is the hard problem, not discovery.** Automated discovery + AI extraction will find
  10× more candidates *and* 10× more junk. The Validator/Scorer + dedup + human-gate are where
  the product lives or dies. Under-invest there and the catalog fills with entertainment,
  duplicates, and hallucinated events.
- Maintenance shifts from linear ("add a provider") to systemic ("tune queries/classifiers/
  validators, watch precision"). Lower total effort, higher skill.

## Recommendation (phased, if pursued)

1. **Phase D1 — Structured discovery loop** (highest ROI, lowest risk): Feed Detector +
   auto-populated registry + link-graph expansion from existing organizers. Deterministic,
   high-precision, no LLM/search-API cost. Realizes "the registry writes itself" for
   JSON-LD/RSS/ICS/sitemap sources.
2. **Phase D2 — Search-engine discovery**: add Google Programmable Search (free tier) with
   query templates → unlock the indexed long tail (Meetup/university/community). Human-gate new
   sources initially; auto-register above a precision threshold once trusted.
3. **Phase D3 — AI extraction**: Gemini classifier + unstructured-HTML extractor (grounded) for
   the no-feed sources; organizer clustering + query generation to name and complete ecosystems.
4. **Always-on:** the Validator/Scorer + dedup + a lightweight human "provider inbox" as the
   permanent quality spine.

**Bottom line:** EventScout should stop being *"a curated list of providers"* and become *"a
crawler + classifier that grows its own catalog."* The technology to do this is publicly
accessible; the real investment is **precision and quality control**, not scraping. That is the
architecture that makes "India's largest professional tech-events platform" a continuously-
growing system rather than a manually-maintained list.
