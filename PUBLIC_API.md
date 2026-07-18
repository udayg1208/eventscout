# Public API (Phase 6A)

The public surface of EventScout: every method on `PlatformService`
(`backend/app/platform/service.py`). This is the **only** entry point a consumer (HTTP API,
frontend, or a future mobile/GraphQL/partner surface) calls. Every method returns a **DTO**
from `app/platform/dto.py` — internal models (`Event`, `StoredEvent`, `EventEnrichment`,
`OrganizerProfile`) are never exposed.

All methods are synchronous except `search` and the `from_repository` constructor. Read paths
operate on projections built once at construction; `now` comes from the injected clock.

## Construction

```python
platform = await PlatformService.from_repository(repo)          # production
platform = PlatformService(repo, events_by_key=…, enrichment=…, graph=…, clock=…)  # injected
```

## DTOs

```python
EventDTO(key, title, url, category, start_date, end_date, city, is_online,
         is_free, price, provider, description)

AIMetadataDTO(topics, technologies, skills, audiences, difficulty, careers, summary)

EntityProfileDTO(entity_type, name, total_events, active_events, cities, extra)
    # extra: {average_quality, chapters?, communities?, categories?}

EventDetailDTO(event: EventDTO, ai: AIMetadataDTO|None, lifecycle: str,
               trending_score: float, similar: [EventDTO],
               organizer: EntityProfileDTO|None, community: EntityProfileDTO|None,
               city: EntityProfileDTO|None)

RecommendationDTO(event: EventDTO, score: float, reasons: [str])

HomepageDTO(sections: {str: [EventDTO]})

AnalyticsDTO(total_events, cities, communities, organizers, providers, topics,
             technologies, top_topics, top_technologies, top_communities)
```

---

## 1 · Homepage

```python
homepage(*, user_id: str | None = None, city: str | None = None, per_section: int = 8) -> HomepageDTO
```

Returns up to **17 sections**, each a `[EventDTO]` capped at `per_section`:

| Section key | Source engine |
|---|---|
| `trending` | Trending Engine (4D) |
| `upcoming` | `filters.upcoming` |
| `ai_events` | category = `ai` |
| `hackathons` | category = `hackathon` |
| `conferences` | category = `conference` |
| `meetups` | category = `meetup` |
| `workshops` | category = `workshop` |
| `startup_events` | category = `startup` |
| `developer_festivals` | title match `devfest` *(no category exists — title-matched)* |
| `government_tech` | title match `government|govt|gov` *(honest gap — title-matched)* |
| `university_events` | title match `university|college|campus|student` *(honest gap)* |
| `recently_added` | `filters.recently_added` (first-seen ≤ 7d) |
| `registration_closing` | lifecycle = `registration_closing` (4D) |
| `online_events` | `is_online = True` |
| `free_events` | `is_free = True` |
| `nearby_events` | present **only if** `city` given |
| `recommended` | present **only if** `user_id` given (User Intelligence 5B) |

---

## 2 · Browse

```python
browse_by_category(category, *, limit=20)   -> [EventDTO]   # "conference", "ai", …
browse_by_city(city, *, limit=20)           -> [EventDTO]   # normalized city match
browse_by_topic(topic, *, limit=20)         -> [EventDTO]   # 5A topic, e.g. "Artificial Intelligence"
browse_by_technology(tech, *, limit=20)     -> [EventDTO]   # 5A tech, e.g. "Python"
browse_by_difficulty(difficulty, *, limit=20) -> [EventDTO] # "Beginner" | "Intermediate" | "Advanced"
browse_by_audience(audience, *, limit=20)   -> [EventDTO]   # e.g. "Students"
browse_by_format(*, online: bool, limit=20) -> [EventDTO]
browse_by_date(*, start: date, end: date, limit=20) -> [EventDTO]
browse_by_community(name, *, limit=20)      -> [EventDTO]   # via Entity Graph (3F)
browse_by_organizer(name, *, limit=20)      -> [EventDTO]   # via Entity Graph (3F)
```

All are scoped to upcoming events and sorted soonest-first. Unknown entity → `[]`.

---

## 3 · Discovery

```python
discover_trending(*, limit=20)              -> [EventDTO]   # capped at 10 by the engine
discover_popular(*, limit=20)               -> [EventDTO]   # proxy: source quality + completeness
discover_newest(*, limit=20)                -> [EventDTO]   # by first_seen_at desc
discover_registration_closing(*, limit=20)  -> [EventDTO]
discover_this_weekend(*, limit=20)          -> [EventDTO]
discover_this_month(*, limit=20)            -> [EventDTO]
discover_online(*, limit=20)                -> [EventDTO]
discover_offline(*, limit=20)               -> [EventDTO]
discover_free(*, limit=20)                  -> [EventDTO]
discover_paid(*, limit=20)                  -> [EventDTO]
discover_nearby(city, *, limit=20)          -> [EventDTO]
```

---

## 4 · Recommendations  *(exposes Phase 5B)*

```python
record_interaction(interaction: Interaction) -> None
recommendations(user_id, *, limit=10) -> [RecommendationDTO]
```

`recommendations` returns deterministic, **explained** results (`reasons`), excluding events
the user already saved/attended. Unknown user → `[]`. `record_interaction` feeds the User
Intelligence Engine (search / view / save / register / attend / ignore) so the profile learns.

Example:
```python
platform.record_interaction(Interaction("u1", InteractionType.ATTEND, now, event_key=k))
recs = platform.recommendations("u1", limit=5)
# [ RecommendationDTO(event=EventDTO(...), score=0.87,
#     reasons=["Recommended because you're interested in Artificial Intelligence.", …]) ]
```

---

## 5 · Search  *(exposes Phase 4B)*

```python
await search(query: SearchQuery, *, limit=20) -> [EventDTO]
```

Runs the full Phase-4B retrieval pipeline (plan → keyword/structured/entity retrieve → RRF
fuse → load → filter → rank) against the Repository and maps ranked events to DTOs. Never
fetches live providers.

```python
SearchQuery(keywords=["kubernetes"], city="Bangalore", categories=[EventCategory.MEETUP],
            date_from=None, date_to=None, free_only=False)
```

---

## 6 · Entity profiles  *(exposes Phase 3F)*

```python
community_profile(name)  -> EntityProfileDTO | None   # extra.chapters = active-in city ids
organizer_profile(name)  -> EntityProfileDTO | None
series_profile(name)     -> EntityProfileDTO | None
city_profile(name)       -> EntityProfileDTO | None   # extra.communities, extra.categories
```

Names resolve through the deterministic `EntityResolver`; unresolved → `None`.

---

## 7 · Analytics  *(read-only)*

```python
analytics() -> AnalyticsDTO
```

```python
AnalyticsDTO(total_events=98, cities=12, communities=7, organizers=9, providers=7,
             topics=20, technologies=18,
             top_topics=[("Artificial Intelligence", 21), …],
             top_technologies=[("Python", 14), …],
             top_communities=[("Google Developer Groups", 12), …])
```

Pure counts derived from the graph + enrichment + organizer profiles. No writes.

---

## 8 · Event details

```python
event_details(key) -> EventDetailDTO | None
```

Assembles the full view for one event: the event, its AI metadata (5A), lifecycle state and
trending score (4D), similar events (5A), and the organizer / community / city profiles (3F).
Unknown key → `None`.

---

## 9 · Similar events

```python
similar_events(key, *, limit=10) -> [EventDTO]
```

Topic/technology/skill overlap + category/community bonuses (5A `EventSimilarity`), excluding
the event itself.

---

## Future interfaces (declared, not implemented)

`app/platform/interfaces.py` commits the shape of the next surfaces; each is a thin adapter
over this facade returning the same DTOs:

`MobileApp` · `PublicAPI` · `GraphQLSchema` · `PartnerAPI` · `AIAssistant` ·
`CalendarIntegration` · `VoiceAssistant`

See [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) for how they fit.
