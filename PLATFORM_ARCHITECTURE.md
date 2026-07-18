# Platform Architecture (Phase 6A)

The **Public EventScout Platform** — the single orchestration layer that turns the internal
engines built in Phases 3–5 into one coherent public product surface. It is a *composition*
layer: it owns no business logic, no storage, no ranking, no intelligence. It wires the
existing engines together and maps every result to a **DTO** so internal models never cross
the boundary.

Code: `backend/app/platform/` — `service.py`, `dto.py`, `filters.py`, `interfaces.py`.

## Where it sits

```
        Frontend / HTTP API / (future) mobile · public API · GraphQL · AI assistant
                                     │
                                     ▼
                           ┌───────────────────┐
                           │  PlatformService  │   ← the ONLY public entry point
                           │   (facade, 6A)    │      returns DTOs, never internal models
                           └───────────────────┘
             ┌───────────┬───────────┼───────────┬─────────────┬───────────┐
             ▼           ▼           ▼           ▼             ▼           ▼
        Search 4B   Intelligence  User Intel   AI Under-    Entity Graph  Repository
      (DatabaseS.   4D (trending  5B (Recommend standing 5A  3F (organizer/ (source of
       Provider)     /lifecycle/   -ation       (enrichment/  community/    truth —
                     freshness)    Engine)      similarity)   series/city)  StoredEvent)
```

Every arrow already existed before 6A. The platform does not reach *past* these engines into
SQLite, the search index, or the frozen `Event` model — it calls the same public methods the
Phase-5 tests call, and adapts the output.

## The one facade

`PlatformService` is constructed once and holds **shared projections** built a single time:

| Held state | Built from | Used by |
|---|---|---|
| `events_by_key: dict[str, StoredEvent]` | `repo.iterate(active_only)` | every read path |
| `enrichment: dict[str, EventEnrichment]` | `EnrichmentPipeline.enrich_events` (5A) | browse-by-topic/tech, AI metadata, similarity |
| `graph` | `GraphBuilder().build` (3F) | entity profiles, entity browse, event details |
| `EntityQueries` | graph + `EntityResolver` | events-by-community / organizer |
| `TrendingEngine` | — (4D) | trending / popular / event-detail score |
| `EventSimilarity` | enrichment + graph (5A) | similar events, event details |
| organizer/community/series `profiles` | `build_organizer_profiles` (4D) | entity profiles, analytics |
| `UserIntelligenceEngine` | events + enrichment + graph (5B) | recommendations, interaction recording |
| `DatabaseSearchProvider` | repo (4B) | `search()` |

Two constructors:

- `await PlatformService.from_repository(repo, clock=…)` — production path: iterates the
  catalog once, derives the graph + enrichment, wires every engine.
- `PlatformService(repo, events_by_key=…, enrichment=…, graph=…, clock=…)` — direct
  injection, used by tests and by any caller that already holds the projections.

The `clock` is injectable (`() -> datetime`); the search provider is given `() ->
clock().date()` so *time is deterministic across the whole facade* — the same `now` drives
lifecycle, trending, freshness, recommendation candidacy, and search's "upcoming" scoping.

## Request flow

Every method is the same three-step shape — **delegate → select → map** — with no rules of
its own:

```
homepage(user_id, city)
   → filters.by_category / TrendingEngine.top / filters.registration_closing / …   (delegate)
   → slice each to per_section                                                     (select)
   → to_event_dto(...) for every StoredEvent                                       (map → DTO)
   ⇒ HomepageDTO{ sections: {name: [EventDTO]} }

event_details(key)
   → enrichment[key] · lifecycle_state · TrendingEngine.score · EventSimilarity
     · graph neighbors (organizer/community/city)                                  (delegate)
   → to_event_dto / to_ai_dto / to_entity_profile_dto                              (map → DTO)
   ⇒ EventDetailDTO

search(query)
   → DatabaseSearchProvider.search(query)  → ranked [Event]                        (delegate, 4B)
   → look each Event up in events_by_key by event_key(event)                       (select)
   → to_event_dto(...)                                                             (map → DTO)
   ⇒ [EventDTO]
```

`filters.py` holds the pure selection predicates (`upcoming`, `by_category`, `by_city`,
`by_topic`, `registration_closing`, `this_weekend`, …). They **reuse** Phase-4D
`lifecycle_state`, Phase-5A enrichment, and `normalize_city` — they invent no new rule; they
only compose existing outputs. This is the one place tempted to grow business logic, so it is
deliberately kept to one-line predicates over already-computed values.

## API grouping

The facade exposes nine groups (detailed in [PUBLIC_API.md](PUBLIC_API.md)):

1. **Homepage** — `homepage()` → 17 sections (15 always-on + `nearby_events` when a city is
   given + `recommended` when a user is given; three are title-matched — see gaps below).
2. **Browse** — `browse_by_{category,city,community,organizer,technology,topic,difficulty,audience,format,date}`.
3. **Discovery** — `discover_{trending,popular,newest,registration_closing,this_weekend,this_month,online,offline,free,paid,nearby}`.
4. **Recommendations** — `recommendations(user_id)` + `record_interaction()` (exposes 5B).
5. **Search** — `search(query)` (exposes 4B).
6. **Entity** — `community_profile / organizer_profile / city_profile / series_profile`.
7. **Analytics** — `analytics()` (read-only counts).
8. **Event details** — `event_details(key)`.
9. **Similar** — `similar_events(key)`.

## The DTO boundary

`dto.py` defines the only shapes that cross the boundary: `EventDTO`, `AIMetadataDTO`,
`EntityProfileDTO`, `EventDetailDTO`, `RecommendationDTO`, `HomepageDTO`, `AnalyticsDTO`.
Mappers (`to_event_dto`, `to_ai_dto`, `to_entity_profile_dto`, `to_recommendation_dto`)
convert internal → DTO. A test (`test_platform_never_exposes_internal_models`) asserts the
frozen `Event`/`StoredEvent` never appear in any response. This keeps the public contract
stable while the internals (storage engine, ranking, enrichment method) evolve freely.

## Future evolution

`interfaces.py` commits the *shape* of every future surface without building
transport/auth/deployment: `MobileApp`, `PublicAPI`, `GraphQLSchema`, `PartnerAPI`,
`AIAssistant`, `CalendarIntegration`, `VoiceAssistant`. Each is a thin adapter over the same
facade returning the same DTOs — exactly how the existing frontend and HTTP API already
depend on `SearchService`. None adds logic; each re-expresses DTOs in another protocol.

## Constraints honored

- **No frozen contract touched** — zero files modified outside `app/platform/`. The platform
  reads Search 4B, Intelligence 4D, User Intelligence 5B, AI Understanding 5A, Entity Graph
  3F, and the Repository through their existing public methods.
- **No new frontend, auth, notifications, API gateway, deployment.**
- **No database / search / repository redesign** — the Repository stays the source of truth;
  the graph and enrichment are rebuildable projections, as before.
- **No business-logic duplication** — ranking stays in 4B, trending/lifecycle in 4D,
  recommendation scoring in 5B, enrichment in 5A, entity resolution in 3F.

## Honest limitations

- **Two homepage slots are best-effort gaps.** *Government Tech Events* and *University
  Events* have no category in the frozen `Event` model, so they are matched by title keyword
  (`government|govt|gov`, `university|college|campus|student`). Coverage is only as good as
  the title text — this is a data-model limit, not a bug, and is documented rather than faked.
  *Developer Festivals* is likewise title/`devfest`-matched (no "festival" category exists).
- **Projections are full rebuilds.** `from_repository` builds the graph + enrichment for the
  whole active catalog in memory. That matches every prior phase; an incremental/outbox
  refresh is the future production step (already the documented path for 3F/5A).
- **`discover_trending` is capped at `trending_top_n` (10)** by the Trending Engine's own
  contract — trending is a small curated set by design; larger limits return at most 10.
- **`discover_popular` is a proxy.** With no engagement data yet (documented since 4D), it
  ranks by source quality + content completeness, not real popularity. It becomes a true
  signal when `EngagementSignal` (4D) is fed.
- **In-process only.** 6A ships the facade + DTOs; the mobile/public/GraphQL/partner/AI/
  calendar/voice surfaces are interfaces, not implementations (by scope).
