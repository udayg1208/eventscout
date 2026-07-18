# Domain → Implementation Mapping

**The final planning document. After approval, implementation resumes and architecture
documents stop.** This maps every major concept in
[PRODUCT_DOMAIN_ARCHITECTURE.md](PRODUCT_DOMAIN_ARCHITECTURE.md) onto the current codebase
and its evolution. No production code — this is the spec the phases are built against.

**How to read each block**
- **Current** — what exists today (real files).
- **Limitations** — why it is not yet the final form.
- **Intermediate** — the next 1–3 phases.
- **Final** — the mature form from the domain architecture.
- **Migration** — how we get there without breaking frozen contracts.
- **Unchanged** — the invariant that holds the whole way.

The governing rule of the migration: **the abstraction seams stay; the implementations
behind them are replaced.** Nothing downstream of a seam is rewritten when what sits behind
it changes.

---

## Part 1 — Concept Mappings

### CATALOG & DATA

#### 1. Opportunity
- **Current:** `Event` — a frozen, normalized Pydantic record ([app/models/event.py](backend/app/models/event.py)); one flat record per source result.
- **Limitations:** event-shaped (single `start_date`/`end_date`, `is_free`/`price` assume cost flows *from* the user, closed `EventCategory` enum); no notion of "the same opportunity seen by several sources."
- **Intermediate:** a **Canonical Opportunity** distinct from the **Source Records** it was assembled from; still event-centric fields but with identity, lifecycle `status`, and `version`.
- **Final:** a node in the **Opportunity Graph** — generalized typed temporal/value/eligibility, connected to Organizations, People, Topics, Places, with per-field provenance.
- **Migration:** keep `Event` as the record shape through Phase 3–4; in Phase 5 generalize it to `Opportunity` with a narrow canonical core + flexible attributes, keeping an Event-compatible projection so the frozen API/frontend survive.
- **Unchanged:** it is always an **immutable, provider-agnostic, normalized record** that every source maps into. That pattern never changes — only its fields widen.

#### 2. Provenance / Source Record
- **Current:** every record carries a `provider` string; the raw source result is discarded after normalization.
- **Limitations:** no memory of *what each source said*; a merge/dedup throws data away; can't resolve conflicts ("source A moved the deadline").
- **Intermediate:** **Source Records** persisted per provider, then resolved into a canonical Opportunity that records which sources contributed.
- **Final:** **per-field provenance + confidence** ("deadline last confirmed by 3 sources 2h ago"), full audit and correction.
- **Migration:** introduced in Phase 3 when ingestion persists raw-then-canonical; deepened to per-field in Phase 9–10.
- **Unchanged:** `provider` provenance is stamped on every record from day one — it only grows richer.

#### 3. Organization
- **Current:** none (organizers appear only as free-text inside events, if at all).
- **Limitations:** no first-class hosts/sponsors/funders; can't offer "follow this company."
- **Intermediate:** a nascent Organization entity extracted during enrichment, loosely linked to opportunities.
- **Final:** a **canonical graph node** (company/university/community/government as facets), entity-resolved across sources, with profile pages and reputation.
- **Migration:** begins in Phase 5 (as the model generalizes), matures in Phase 9 (Organization Profiles).
- **Unchanged:** n/a (new capability) — but it reuses the same canonical-vs-source + entity-resolution machinery built for Opportunity.

#### 4. Person
- **Current:** none.
- **Limitations:** no speakers/mentors/recruiters as entities; no people-graph features.
- **Intermediate:** nascent Person entity from enrichment (speakers/organizers on opportunities).
- **Final:** canonical **Person graph node** with roles (speaker/mentor/recruiter/founder), entity-resolved, possibly linked to a User.
- **Migration:** Phase 5 seed → Phase 9 profiles → Phase 10 career graph.
- **Unchanged:** reuses Opportunity's resolution/provenance pattern.

#### 5. Taxonomy — Category / Topic / Skill
- **Current:** `EventCategory` StrEnum (7 values) + `classify_category` keyword refinement ([app/providers/classify.py](backend/app/providers/classify.py)); topics/skills absent.
- **Limitations:** closed enum requires a code change per new type; **conflates format** (meetup/conference) **with topic** (ai/startup); no hierarchy, no skills.
- **Intermediate:** a **Taxonomy Engine** — types/categories/topics as governed *data*, with mapping from messy source labels to canonical concepts; classification reads the taxonomy.
- **Final:** a versioned **ontology** (topic hierarchy + skills graph, multilingual) powering matching and career paths.
- **Migration:** Phase 5 externalizes the enum into taxonomy data and splits type from topic; Phase 7+ adds the skills ontology for matching.
- **Unchanged:** the principle that a record is always assigned a canonical classification at write time.

#### 6. Location / Venue
- **Current:** `city`/`location` strings + `normalize_city`/`detect_city` ([app/city.py](backend/app/city.py)).
- **Limitations:** string-based, flat, no region hierarchy or venue identity.
- **Intermediate:** a **Location resolution** step producing canonical geography; Venue as a light entity.
- **Final:** hierarchical geo graph (city→region→country→global), venue reputation, travel/visa-aware eligibility.
- **Migration:** the existing normalization functions become the seed of Location resolution in Phase 5.
- **Unchanged:** `normalize_city`/`detect_city` remain the reusable pure resolvers; only what they feed grows.

---

### INGESTION & SOURCING

#### 7. Provider
- **Current:** `EventProvider` ABC (async `search`) + 7 concrete providers, hand-wired in `get_provider()` ([app/providers/](backend/app/providers/)).
- **Limitations:** fetch is triggered by user search; "give me everything" is an implicit empty-query convention; no declared operational metadata; providers hand-listed.
- **Intermediate:** **Ingestion Plugins** — each existing provider wrapped with **declared metadata** (refresh interval, timeout, retry, rate limit, concurrency, priority, incremental/pagination flags) and an explicit "fetch all" capability, run by the scheduler.
- **Final:** a **Provider Ecosystem** — hundreds of sources, partner-submitted and user-submitted feeds, data-driven trust weighting, a provider template/SDK, automated health gating.
- **Migration:** Phase 3 wraps today's providers as plugins **unchanged** (reused via their existing fetch), adds a registry + metadata; the ecosystem grows continuously from Phase 5 on.
- **Unchanged:** the **source-adapter boundary** (a source maps its shape into the canonical record) and the **normalize-at-the-boundary** rule are permanent.

#### 8. Deduplication
- **Current:** deterministic rapidfuzz engine — title/url similarity with date+city gates, cluster, keep-richest ([app/providers/dedup.py](backend/app/providers/dedup.py)).
- **Limitations:** runs in-memory over one search's batch only; discards duplicates instead of recording them; O(n²) risk on large blocks.
- **Intermediate:** **Entity Resolution** — the same similarity logic applied at write time against DB candidates (blocked by date/city), producing a canonical record + a duplicate group + provenance, instead of dropping rows.
- **Final:** the **Canonical Opportunity Graph** — learned resolution across Opportunities, Organizations and People, conflict resolution, cluster identity.
- **Migration:** Phase 3 moves the existing pure similarity functions from the search path to the ingestion write path and stores cluster identity + provenance; Phase 9–10 upgrades matching from rules to learned models.
- **Unchanged:** the **pure, deterministic similarity functions** (`normalize_title`, `title_similarity`, etc.) are reusable building blocks throughout.

#### 9. Classification
- **Current:** `classify_category` — high-precision keyword regexes refining generic events ([app/providers/classify.py](backend/app/providers/classify.py)).
- **Limitations:** hardcoded taxonomy in regexes; format/topic conflation; no topics/skills.
- **Intermediate:** the **Taxonomy Engine** — deterministic classification against taxonomy *data*, inline and cheap on the write path.
- **Final:** **AI Enrichment** — embeddings-driven topic/skill extraction and refined classification, asynchronous and best-effort, upgrading (never blocking) the cheap inline label.
- **Migration:** Phase 5 taxonomy-izes classification; Phase 7/AI-enrichment adds the semantic layer as an async projection.
- **Unchanged:** a record always gets *a* usable classification at write time (search never waits on AI).

#### 10. Enrichment
- **Current:** none (only inline city-normalize + classify inside the composite).
- **Limitations:** no derived meaning — no embeddings, tags, quality scores, extracted entities.
- **Intermediate:** basic asynchronous enrichment (tags, quality score, geocode) after persist.
- **Final:** an **AI Enrichment Service** — embeddings, entity extraction (orgs/people), skill mapping, quality/trust scoring, LLM re-classification — idempotent workers, never on the hot path.
- **Migration:** introduced as async workers once the catalog is the source of truth (Phase 3 seam, real work from Phase 7).
- **Unchanged:** the AI-safety invariant — enrichment **refines existing data; it never fetches or invents opportunities.**

#### 11. Scheduler
- **Current:** none (no background execution).
- **Limitations:** no automatic refresh; freshness = cache TTL paid by the user.
- **Intermediate:** a **metadata-driven scheduler** — reads each plugin's declared metadata + stored health, selects due providers from a persisted schedule, runs them under bounded concurrency with retry/backoff/rate-limit/circuit-breaker, plus expiry/archive jobs.
- **Final:** a **Distributed Ingestion Platform** — durable task queue + horizontally-scaled workers, near-real-time tiers, priority fairness across hundreds of providers.
- **Migration:** Phase 3 builds the in-process metadata-driven scheduler behind a dispatch seam; the dispatch mechanism swaps to a queue when metrics fire — scheduling *policy* is unchanged.
- **Unchanged:** scheduling **policy is metadata-driven, never hardcoded per provider** — permanent.

#### 12. Sync Job / Provider Health
- **Current:** on-demand `analytics/provider_analytics.py` samples live fetches; no persisted per-provider state.
- **Limitations:** point-in-time only; no checkpoints, no continuous health, no next-run state.
- **Intermediate:** persisted **sync state** (checkpoints/watermarks for delta sources) + **provider health** (success/latency/volume/circuit) recorded every run.
- **Final:** continuous observability — anomaly detection (volume→0), auto-throttle, auto-retirement, source trust weighting.
- **Migration:** Phase 3 introduces the provider-state store; analytics reads it instead of live-sampling.
- **Unchanged:** the analytics *interface* concept (aggregate → render) carries over; its data source moves from live fetch to the store.

---

### STORAGE & RETRIEVAL

#### 13. Repository
- **Current:** `SQLiteEventRepository` behind the `EventRepository` abstraction ([app/storage/](backend/app/storage/), Phase 3A).
- **Limitations:** MVP surface — row-by-row upsert, no keyset pagination/streaming, `all()` footgun, `is_active` boolean conflates lifecycle states, no sync-state/health, single-writer/file-local.
- **Intermediate:** **Storage Abstraction v2** — bulk upsert, keyset pagination, streaming iteration, `status` lifecycle + archive, provider-state store, versioning; SQLite first, then a durable Postgres implementation of the *same* abstraction.
- **Final:** a **Distributed Repository / Catalog** — the partitioned, replicated system of record with JSONB-flexible attributes and archival, read-scaled behind the unchanged abstraction.
- **Migration:** Phase 3 = Repository v2 (SQLite); Phase 4 = Postgres implementation (durability + concurrency + partitioning); no application code changes — only which implementation is constructed.
- **Unchanged:** the **repository abstraction is storage-agnostic**; the app never depends on a concrete backend. This seam is permanent.

#### 14. Search
- **Current:** `CompositeProvider` fan-out + in-memory filter + `rank` ([app/providers/composite.py](backend/app/providers/composite.py)).
- **Limitations:** searches by fanning out to live providers; `LIKE`-style filtering won't scale (full scan); ranks the whole set in memory.
- **Intermediate:** **Repository Search** — a DB-backed provider reads the catalog through the abstraction (one indexed query), returned behind the *same* provider contract so `SearchService` and the API are untouched; add full-text search.
- **Final:** a **Search Index + Retrieval Pipeline** — semantic + keyword + faceted retrieval from a rebuildable index projection, two-phase retrieve-top-K-then-re-rank, typo-tolerant and multilingual.
- **Migration:** Phase 3 flips `get_provider()` to the DB-backed search (warm the catalog first); Phase 4 adds FTS then an external/vector index as a projection.
- **Unchanged:** search is exposed through the **`EventProvider`/provider contract** and `SearchService` — the read edge stays stable while what's behind it is replaced.

#### 15. Ranking / Matching
- **Current:** deterministic weighted scorer — relevance/date/location/source/popularity/completeness ([app/providers/ranking.py](backend/app/providers/ranking.py)).
- **Limitations:** query-only (no user context); `score_source` hardcodes per-provider quality; scores the full candidate set.
- **Intermediate:** **preference-aware ranking** — the same weighted pipeline extended to consume a user profile and data-driven source quality; two-phase over a bounded candidate set.
- **Final:** **Matching Intelligence** — embedding-based person↔opportunity match, outcome-calibrated, explainable.
- **Migration:** ranking stays a **separable read-side stage** so a profile signal and index candidates slot in (Phase 7) without touching retrieval or storage.
- **Unchanged:** ranking is an isolated, pure, weights-in-one-place stage — that separation is permanent.

#### 16. Query Understanding
- **Current:** `QueryParser` seam — `GeminiQueryParser` (validate → retry → deterministic fallback) + `KeywordQueryParser` ([app/parsers/](backend/app/parsers/)).
- **Limitations:** maps to today's `SearchQuery` fields only; no intent beyond filters; no profile awareness.
- **Intermediate:** the same seam extended to richer intent (types/topics/skills) and, later, profile-aware disambiguation.
- **Final:** natural-language + agentic intent understanding over the graph, feeding both search and the assistant.
- **Migration:** the seam and its AI-safety contract carry forward unchanged; only the target query vocabulary widens with the taxonomy.
- **Unchanged:** the **QueryParser seam + AI-safety invariant** — the LLM understands the query and never fetches or fabricates opportunities; a validated fallback always exists. Permanent.

#### 17. Cache
- **Current:** generic `TTLCache` (injectable clock) — parse-cache + results-cache in `SearchService` ([app/cache.py](backend/app/cache.py)).
- **Limitations:** per-process, in-memory, size-uncapped.
- **Intermediate:** caching becomes a read-side concern over the repository/index (query + projection caching).
- **Final:** a distributed cache / CDN edge for hot reads.
- **Migration:** the cache is already injected and generic; its implementation swaps without touching `SearchService`.
- **Unchanged:** caching stays an injected, invisible-to-callers concern.

---

### USERS, ENGAGEMENT & INTELLIGENCE

#### 18. Users / Identity
- **Current:** none (stateless, anonymous).
- **Limitations:** nothing is personal; no accounts, no persistence of user intent.
- **Intermediate:** **Profiles** — accounts, authentication, preferences, consent.
- **Final:** **AI Career Profiles** — a semantic understanding of goals/skills/stage built from explicit input + behavior.
- **Migration:** Phase 6 adds identity (a *generic* subdomain — standardize, don't over-build); the profile becomes semantic in Phase 7.
- **Unchanged:** n/a (new). Identity is deliberately generic so effort concentrates on the AI Profile (core).

#### 19. AI Profile
- **Current:** none.
- **Limitations:** no personalization signal exists.
- **Intermediate:** a **preference profile** (explicit topics/locations/types + captured interactions).
- **Final:** the **semantic career profile** — embeddings of interests/skills/goals, the counterpart to an Opportunity in matching; privacy-governed.
- **Migration:** Phase 6 captures interactions cleanly; Phase 7 builds the semantic profile.
- **Unchanged:** **user interactions are captured cleanly and privately from the first user** — the flywheel's fuel.

#### 20. Recommendations
- **Current:** none.
- **Limitations:** discovery is pull-only; no personalization.
- **Intermediate:** **preference-aware ranking** — recommendations as personalized ordering of catalog results.
- **Final:** a **Personalized Opportunity Feed** — proactive, predictive, outcome-calibrated matching per user.
- **Migration:** Phase 7 joins AI Profile ↔ catalog via the matching stage; deepens as outcome data accrues.
- **Unchanged:** recommendation is a read-side projection over the same catalog — no separate source of truth.

#### 21. Engagement — Bookmark / Application / Outcome
- **Current:** none (frontend has ephemeral local history only).
- **Limitations:** no saved state, no application tracking, no outcomes → no feedback loop.
- **Intermediate:** **bookmarks/collections + saved searches + application tracking**.
- **Final:** full lifecycle — Application → **Outcome**, the unique compounding dataset feeding matching and trust.
- **Migration:** Phase 6 adds bookmarks/applications; Phase 7 captures outcomes into the flywheel.
- **Unchanged:** n/a (new) — but engagement events flow into the same event backbone.

#### 22. Notifications
- **Current:** none.
- **Limitations:** the platform can't reach out; no alerts or reminders.
- **Intermediate:** **Saved Searches** matched against new/updated opportunities → basic alerts.
- **Final:** **Real-time Opportunity Alerts** — multi-channel, deadline-aware reminders, intelligently timed; a *generic* delivery capability.
- **Migration:** Phase 8 matches catalog events against saved searches/profiles → notifications.
- **Unchanged:** n/a (new) — reacts to catalog events like every other projection.

#### 23. Analytics
- **Current:** `provider_analytics.py` — live-sampled provider scorecard (`PROVIDER_ANALYTICS.md`).
- **Limitations:** operational only, live-fetch, point-in-time; no growth/freshness/behavioral intelligence.
- **Intermediate:** **Operational Analytics** — coverage/freshness/growth/health computed incrementally from the catalog + provider-state store.
- **Final:** **Platform Intelligence** — trends, market insights, outcome analytics, B2B/partner reporting off a read replica.
- **Migration:** Phase 3 re-points analytics at the store; Phase 10 adds behavioral/trend intelligence.
- **Unchanged:** the **aggregate → render** split (pure computation separated from data source) carries forward.

#### 24. Quality / Trust
- **Current:** implicit only — a hardcoded per-provider source-quality weight inside ranking.
- **Limitations:** not a real score; no spam/decay/duplicate defense; unmaintainable at scale.
- **Intermediate:** a **trust/quality score** per opportunity/source (completeness + corroboration + freshness), gating search/recs.
- **Final:** **Trust & Safety** — automated spam/decay detection, moderation workflows, data-driven source trust.
- **Migration:** Phase 3 derives source quality from health data (replacing the hardcoded weight); scoring deepens from Phase 5.
- **Unchanged:** the principle that quality gates what users see.

#### 25. Search Index
- **Current:** none (no separate index).
- **Limitations:** search relies on scans; no semantic retrieval.
- **Intermediate:** a **full-text index** as a rebuildable projection of the catalog.
- **Final:** an **external + vector index** (typo-tolerant, faceted, semantic) updated from the catalog via the event backbone.
- **Migration:** Phase 4 adds FTS; a dedicated engine when retrieval scale/quality demands it.
- **Unchanged:** the index is always a **rebuildable projection**, never a second source of truth.

#### 26. API / Contracts
- **Current:** `POST /search` (NL) + `/events/search` (structured), consumed by the Next.js frontend; frozen.
- **Limitations:** a single consumer surface; no ingestion/admin/partner/agent contracts; event-shaped payloads.
- **Intermediate:** the discovery contract stays stable; internal ingestion/admin surfaces appear.
- **Final:** the full contract set — Discovery, Profile, Ingestion/Provider, Partner/B2B, **Intelligence/Agent**, Governance, and the internal **domain-event** backbone.
- **Migration:** the frozen discovery contract is preserved (versioned/projected when Opportunity generalizes); new contracts are added, not retrofitted.
- **Unchanged:** consumers depend on a **stable published contract**; contexts integrate via **events, not shared state**. Permanent.

---

## Part 2 — Roadmap: Implementation Phases → Business Capabilities

Each phase delivers user-visible or operator-visible value; heavy infrastructure (Postgres,
queue, external index) lands *inside* a phase only when a metric justifies it. Sub-steps
reuse the 3A–3F detail from [PHASE3_ARCHITECTURE_REVIEW.md](PHASE3_ARCHITECTURE_REVIEW.md).

| Phase | Business capability | Delivers | Key domain concepts activated |
|---|---|---|---|
| **3** | **Reliable Data** — a continuously-updated catalog you can trust | Repository v2 → ingestion engine → metadata scheduler → DB-backed search cutover → operational analytics & provider health; dedup becomes write-time Entity Resolution v1 with provenance | Repository, Provider→Plugin, Entity Resolution, Sync Job, Provider Health, Catalog |
| **4** | **Scalable Search** — search that scales to millions | Postgres as the durable source of truth (same abstraction) → full-text index + retrieval pipeline → two-phase ranking → keyset pagination at the edge | Distributed Repository, Search Index, Retrieval, Ranking |
| **5** | **Beyond Events** — every opportunity type | `Event`→`Opportunity` generalization → Taxonomy Engine (types/topics/skills as data) → generalized temporal/value/eligibility → multi-type providers; Organization & Person seeded with provenance | Opportunity, Taxonomy, Location, Organization, Person |
| **6** | **User Accounts & Engagement** — a place to act | Identity + Profiles + preferences/consent → bookmarks/collections → saved searches → application tracking → clean interaction capture | Users, Preferences, Engagement, Interactions |
| **7** | **Recommendations** — a personalized feed | AI Profile (semantic) → preference + embedding matching → Personalized Opportunity Feed → Outcome capture feeding the flywheel; AI Enrichment (embeddings/quality) as async workers | AI Profile, Recommendation, Matching, Enrichment, Outcome |
| **8** | **Notifications** — real-time alerts | Catalog events matched against saved searches/profiles → multi-channel notifications → deadline-aware reminders | Notification, Reminder, Alert |
| **9** | **Organization & People Profiles** — the graph surfaces | Entity resolution for Organizations & People → profile pages → follow → graph-powered discovery ("more from orgs like this") | Organization, Person, Affiliation, the Graph |
| **10** | **Career Intelligence** — outcomes & trends | Skill/career-path graph → outcome-calibrated matching → Platform Intelligence (trends, market insights) → B2B/partner surfaces | Insight/Trend, Skill graph, Trust, Partner |
| **11** | **AI Opportunity Assistant** — conversational & agentic | Natural-language/agentic access over the graph → proactive guidance → Intelligence/Agent contract | Agent API, Matching, Query Understanding, the whole graph |

**Horizontal capabilities** (not a single phase — they escalate across phases): **Trust &
Safety** (from Phase 3, deepening), **Distributed Ingestion / Task Queue + Workers** (extract
when metrics fire, ~Phase 4+), **Observability** (from Phase 3). **Deviation from the example
roadmap:** I inserted **Phase 5 "Beyond Events"** — the Opportunity generalization the product
name depends on — before recommendations/notifications, because personalization and multi-type
value both rest on the generalized model and taxonomy.

---

## Part 3 — Permanent Freezes (already aligned with the final architecture)

These are frozen **permanently** — not "until the next phase." Most are **principles and
seams**, because at this stage principles are what genuinely align with the five-year form;
very little concrete code is truly final. Honest and deliberate.

**Principles (permanent invariants):**
1. **Normalize at the source boundary.** Every source maps its shape into one canonical,
   provider-agnostic, immutable record. ([[provider-abstraction-principle]])
2. **Depend on abstractions, never concretes.** The repository is storage-agnostic; the active
   source/parser is chosen behind a single swap seam. The app never binds to SQLite, Postgres,
   Gemini, or any one provider.
3. **AI-safety invariant.** The LLM understands queries and enriches existing data; it **never
   fetches, searches, or fabricates opportunities**; no results → empty; a validated
   deterministic fallback always exists.
4. **Catalog is the single source of truth; everything else is a rebuildable projection**, and
   contexts integrate through events, not shared state.
5. **Idempotent, content-hash-based writes** — re-ingesting the same data never duplicates or
   corrupts.
6. **Provenance on every record** from day one.
7. **Deterministic, network-free tests** as an engineering standard (source payloads mocked).

**Seams / contracts (permanent — implementations behind them will change, the seams will not):**
8. The **provider/source-adapter contract** (a source produces normalized records).
9. The **query-understanding seam** (`QueryParser`).
10. The **storage abstraction** (`EventRepository` → its v2 successor) as the storage-agnostic port.
11. The **single swap point** pattern (`get_provider()` / factory indirection) that lets the
    active implementation change without touching `SearchService`, the API, or the frontend.
12. The **published discovery contract** the frontend depends on (stable, versioned when the
    model generalizes).

**Reusable pure building blocks (kept and carried forward, not rewritten):**
13. The **similarity functions** in dedup (`normalize_title`/`title_similarity`/… ) — become
    Entity Resolution primitives.
14. **City/location resolvers** (`normalize_city`/`detect_city`) — seed Location resolution.
15. The **ranking stage's isolation** (pure, weights-in-one-constant) — the shape matching
    plugs into.
16. The **analytics aggregate→render split** — data source changes, structure stays.

**Explicitly NOT frozen (the active workspace):** `Event`'s field set and `EventCategory`
enum, `SearchQuery`'s field set, `CompositeProvider`'s internals, what `get_provider()`
returns, the SQLite specifics, the hardcoded `score_source` weights, and the MVP repository
surface from 3A. These are expected to change — freezing them would fight the vision.

---

*Approve this mapping and implementation resumes at **Phase 3 / Repository v2**, built to speak
this document's language. This is the last architecture document.*
