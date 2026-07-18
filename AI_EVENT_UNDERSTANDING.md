# AI Event Understanding (Phase 5A)

Turns every normalized event into an **AI-understood object** — topics, technologies, skills,
audiences, difficulty, careers, and a summary — plus event similarity. Deterministic today,
with interfaces for future LLM enrichment.

## Principle: additive, separate, deterministic

The `Event` model is **never modified**. Enrichment is a distinct `EventEnrichment` object
**keyed by event key** and held in a separate **AI Metadata Store**, so a future Opportunity
model consumes it directly. The layer reads the frozen catalog (+ the Phase-3F entity graph
for community-aware similarity) and writes only into its own store. Nothing frozen —
SearchService, QueryParser, Repository, Search Infrastructure, providers, Intelligence
Engine, API, frontend — is touched. Every output is a pure function of the event text, so it
is reproducible.

## Metadata model

```
EventEnrichment(key, topics[], technologies[], skills[], audiences[],
                difficulty, careers[], summary, method)
```

| Field | How it's produced |
|---|---|
| `topics` | taxonomy regex over title + description (20 canonical topics) |
| `technologies` | taxonomy regex (Python, React, Docker, AWS, LangChain, Claude, …) |
| `skills` | mapped from detected topics + event format (workshop → hands-on, conference → networking) |
| `audiences` | mapped from topics + category + difficulty (defaults to Developers) |
| `difficulty` | Beginner / Intermediate / Advanced from signal words + category prior |
| `careers` | mapped from topics (AI → AI Engineer, Cloud → Cloud Engineer, Startup → Founder) |
| `summary` | deterministic template over difficulty + category + topics + tech + audience |
| `method` | provenance: `deterministic` today, `llm` later |

## Components (`app/enrichment/`)

`taxonomy.py` (topic/tech patterns + skill/audience/career maps + difficulty signals) ·
`extractors.py` (pure extraction functions) · `enricher.py` (`Enricher` ABC +
`DeterministicEnricher`) · `similarity.py` (`EventSimilarity`) · `store.py` (`EnrichmentStore`
+ in-memory) · `pipeline.py` (`EnrichmentPipeline`) · `interfaces.py` (future seams) ·
`models.py`.

## Event similarity

`EventSimilarity.similar_to(key)` scores every other enriched event by
`0.6·Jaccard(topics+tech+skills) + 0.25·same-category + 0.15·same-community`
(community from the entity graph). Deterministic; ties break by key. Live: an AI/LLMs event
surfaces other AI events at score ~0.70.

## Deterministic extraction — and its ceiling (honest)

Extraction reads **only the event text**. Live over the real catalog (98 events): **all 98
enriched, but only 33 have ≥1 topic** — the other ~2/3 have terse titles ("Google Cloud
Arcade Event") and empty descriptions, so there is nothing to match. Top topics: Artificial
Intelligence (18), Generative AI (5), Open Source (5), Startup (4). Top career: AI Engineer
(×21). Difficulty: intermediate 71 / beginner 26 / advanced 1.

This coverage ceiling is the point of the **LLM future**: a language model *understands* an
event without keyword matches, and would enrich the other two-thirds.

## Future LLM evolution (interfaces only — nothing implemented)

`interfaces.py` defines the seams:
- **`LLMEnricher(Enricher)`** — same `EventEnrichment` output shape, so it drops in beside (or
  as a validate→retry→fallback around) the deterministic enricher, honoring the project's
  AI-safety rule: *refine existing data, never fetch or fabricate*. The deterministic result is
  the guaranteed fallback.
- **`Embedder`** → **`SemanticSearchIndex`** — embed the enrichment for semantic search; this
  feeds the Search Infrastructure's existing `SemanticRetriever` seam (Phase 4B) with no change
  there.
- **`Recommender`** — personalized recommendations over enriched events.
- **`AIAssistant`** — conversational access over the enriched catalog.

None are built in 5A. Because enrichment output is a stable, separately-stored object, adding
any of them changes an *implementation*, never the Event model or anything frozen.

## Storage & scale

In-memory `EnrichmentStore` today (keyed by event key), behind an interface so SQLite/Postgres
drops in later. Enrichment is O(1) per event (regex scans); the pipeline is O(catalog) per run
and re-enriches the active set — an incremental hook (re-enrich only changed events, driven by
the Intelligence layer's change detection) is the scale path.
