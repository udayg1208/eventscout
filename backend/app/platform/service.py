"""PlatformService — the single public orchestration service.

Contains **no** business logic: it wires together the existing engines (Search 4B, Entity
Graph 3F, AI Understanding 5A, Intelligence 4D, User Intelligence 5B, Repository) and maps
their outputs to DTOs. Everything a public consumer needs — homepage, browse, discovery,
event details, entity profiles, recommendations, search, analytics — is a method here that
delegates and maps. Nothing frozen is modified.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from app.city import normalize_city
from app.enrichment import EnrichmentPipeline
from app.enrichment.similarity import EventSimilarity
from app.entities.builder import GraphBuilder
from app.entities.models import EdgeType, EntityType
from app.entities.queries import EntityQueries
from app.entities.resolution import EntityResolver
from app.intelligence.lifecycle import lifecycle_state
from app.intelligence.organizers import build_organizer_profiles
from app.intelligence.trending import TrendingEngine
from app.models.search import SearchQuery
from app.platform import filters
from app.platform.dto import (
    AnalyticsDTO,
    EntityProfileDTO,
    EventDetailDTO,
    EventDTO,
    HomepageDTO,
    RecommendationDTO,
    to_ai_dto,
    to_entity_profile_dto,
    to_event_dto,
    to_recommendation_dto,
)
from app.providers.ranking import completeness, score_source
from app.search.db_provider import DatabaseSearchProvider
from app.storage.models import SearchCriteria, StoredEvent, event_key
from app.users.engine import UserIntelligenceEngine
from app.users.models import Interaction


class PlatformService:
    def __init__(
        self,
        repo,
        *,
        events_by_key: dict[str, StoredEvent],
        enrichment: dict,
        graph,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._events = events_by_key
        self._enrichment = enrichment
        self._graph = graph
        self._clock = clock
        self._entity_queries = EntityQueries(graph, EntityResolver())
        self._trending = TrendingEngine()
        self._similarity = EventSimilarity(enrichment, events_by_key, graph=graph)
        self._profiles = build_organizer_profiles(graph, events_by_key, clock())
        self._profiles_by_id = {p.entity_id: p for p in self._profiles}
        self._users = UserIntelligenceEngine(events_by_key, enrichment, graph)
        self._search_provider = DatabaseSearchProvider(repo, clock=lambda: clock().date())

    @classmethod
    async def from_repository(cls, repo, **kwargs) -> PlatformService:
        events = [s async for s in repo.iterate(SearchCriteria(active_only=True))]
        events_by_key = {s.key: s for s in events}
        graph = GraphBuilder().build(events)
        pipeline = EnrichmentPipeline()
        pipeline.enrich_events(events, graph=graph)
        return cls(
            repo,
            events_by_key=events_by_key,
            enrichment=pipeline.store.all(),
            graph=graph,
            **kwargs,
        )

    # --- helpers ---

    def _now(self) -> datetime:
        return self._clock()

    def _dtos(self, events: Iterable[StoredEvent], limit: int | None = None) -> list[EventDTO]:
        events = list(events)
        return [to_event_dto(s) for s in (events[:limit] if limit else events)]

    def _values(self):
        return self._events.values()

    # --- search (delegates to the Search Infrastructure) ---

    async def search(self, query: SearchQuery, *, limit: int = 20) -> list[EventDTO]:
        events = await self._search_provider.search(query)
        stored = [self._events.get(event_key(e)) for e in events]
        return [to_event_dto(s) for s in stored if s is not None][:limit]

    # --- browse ---

    def browse_by_category(self, category: str, *, limit: int = 20) -> list[EventDTO]:
        return self._dtos(filters.by_category(self._values(), category, self._now()), limit)

    def browse_by_city(self, city: str, *, limit: int = 20) -> list[EventDTO]:
        return self._dtos(filters.by_city(self._values(), city, self._now()), limit)

    def browse_by_topic(self, topic: str, *, limit: int = 20) -> list[EventDTO]:
        return self._dtos(
            filters.by_topic(self._values(), self._enrichment, topic, self._now()), limit
        )

    def browse_by_technology(self, technology: str, *, limit: int = 20) -> list[EventDTO]:
        return self._dtos(
            filters.by_technology(self._values(), self._enrichment, technology, self._now()), limit
        )

    def browse_by_difficulty(self, difficulty: str, *, limit: int = 20) -> list[EventDTO]:
        return self._dtos(
            filters.by_difficulty(self._values(), self._enrichment, difficulty, self._now()), limit
        )

    def browse_by_audience(self, audience: str, *, limit: int = 20) -> list[EventDTO]:
        return self._dtos(
            filters.by_audience(self._values(), self._enrichment, audience, self._now()), limit
        )

    def browse_by_format(self, *, online: bool, limit: int = 20) -> list[EventDTO]:
        return self._dtos(filters.by_format(self._values(), online=online, now=self._now()), limit)

    def browse_by_date(self, *, start, end, limit: int = 20) -> list[EventDTO]:
        return self._dtos(
            filters.by_date_range(self._values(), start=start, end=end, now=self._now()), limit
        )

    def browse_by_community(self, name: str, *, limit: int = 20) -> list[EventDTO]:
        return self._entity_events(name, EntityType.COMMUNITY, limit)

    def browse_by_organizer(self, name: str, *, limit: int = 20) -> list[EventDTO]:
        return self._entity_events(name, EntityType.ORGANIZATION, limit)

    def _entity_events(self, name: str, entity_type: EntityType, limit: int) -> list[EventDTO]:
        lookup = {
            EntityType.COMMUNITY: self._entity_queries.events_by_community,
            EntityType.ORGANIZATION: self._entity_queries.events_by_organization,
        }[entity_type]
        stored = [self._events[k] for k in lookup(name) if k in self._events]
        return self._dtos(filters.upcoming(stored, self._now()), limit)

    # --- browse (paginated, whole catalog) ---

    BROWSE_DIMENSIONS = (
        "category",
        "city",
        "topic",
        "technology",
        "difficulty",
        "audience",
        "community",
        "organizer",
        "online",
        "offline",
    )

    def browse_all(self, dimension: str, value: str) -> list[StoredEvent]:
        """Every active event for a browse dimension, ordered upcoming-first then past — the
        complete browsable set (unbounded). Raises KeyError for an unknown dimension. Reuses the
        same predicates as the limited `browse_by_*` methods; only the ordering/limit differ."""
        events = list(self._values())
        enr = self._enrichment
        if dimension == "category":
            matched = [s for s in events if s.event.category.value == value]
        elif dimension == "city":
            target = normalize_city(value).casefold()
            matched = [
                s
                for s in events
                if s.event.city and normalize_city(s.event.city).casefold() == target
            ]
        elif dimension == "online":
            matched = [s for s in events if s.event.is_online]
        elif dimension == "offline":
            matched = [s for s in events if not s.event.is_online]
        elif dimension == "topic":
            matched = [s for s in events if (e := enr.get(s.key)) and value in e.topics]
        elif dimension == "technology":
            matched = [s for s in events if (e := enr.get(s.key)) and value in e.technologies]
        elif dimension == "difficulty":
            matched = [s for s in events if (e := enr.get(s.key)) and e.difficulty.value == value]
        elif dimension == "audience":
            matched = [s for s in events if (e := enr.get(s.key)) and value in e.audiences]
        elif dimension == "community":
            keys = self._entity_queries.events_by_community(value)
            matched = [self._events[k] for k in keys if k in self._events]
        elif dimension == "organizer":
            keys = self._entity_queries.events_by_organization(value)
            matched = [self._events[k] for k in keys if k in self._events]
        else:
            raise KeyError(dimension)
        return filters.browse_order(matched, self._now())

    def browse_page(
        self, dimension: str, value: str, *, offset: int = 0, limit: int = 24
    ) -> tuple[list[EventDTO], int]:
        """A page of a browse dimension plus its full total. Only the returned slice is mapped to
        DTOs, so paging stays cheap even for a 10,000-event catalog."""
        items = self.browse_all(dimension, value)
        total = len(items)
        page = items[offset : offset + limit] if limit else items[offset:]
        return [to_event_dto(s) for s in page], total

    # --- discovery ---

    def discover_trending(self, *, limit: int = 20) -> list[EventDTO]:
        top = self._trending.top(list(self._values()), self._now())
        stored = [self._events[t.key] for t in top if t.key in self._events]
        return self._dtos(stored, limit)

    def discover_popular(self, *, limit: int = 20) -> list[EventDTO]:
        events = filters.upcoming(self._values(), self._now())
        events.sort(key=lambda s: (-(score_source(s.event) + completeness(s.event) / 6), s.key))
        return self._dtos(events, limit)

    def discover_newest(self, *, limit: int = 20) -> list[EventDTO]:
        events = filters.upcoming(self._values(), self._now())
        events.sort(key=lambda s: s.first_seen_at, reverse=True)
        return self._dtos(events, limit)

    def discover_registration_closing(self, *, limit: int = 20) -> list[EventDTO]:
        return self._dtos(filters.registration_closing(self._values(), self._now()), limit)

    def discover_this_weekend(self, *, limit: int = 20) -> list[EventDTO]:
        return self._dtos(filters.this_weekend(self._values(), self._now()), limit)

    def discover_this_month(self, *, limit: int = 20) -> list[EventDTO]:
        return self._dtos(filters.this_month(self._values(), self._now()), limit)

    def discover_online(self, *, limit: int = 20) -> list[EventDTO]:
        return self.browse_by_format(online=True, limit=limit)

    def discover_offline(self, *, limit: int = 20) -> list[EventDTO]:
        return self.browse_by_format(online=False, limit=limit)

    def discover_free(self, *, limit: int = 20) -> list[EventDTO]:
        return self._dtos(filters.by_free(self._values(), free=True, now=self._now()), limit)

    def discover_paid(self, *, limit: int = 20) -> list[EventDTO]:
        return self._dtos(filters.by_free(self._values(), free=False, now=self._now()), limit)

    def discover_nearby(self, city: str, *, limit: int = 20) -> list[EventDTO]:
        return self.browse_by_city(city, limit=limit)

    # --- homepage ---

    def homepage(
        self, *, user_id: str | None = None, city: str | None = None, per_section: int = 8
    ) -> HomepageDTO:
        now = self._now()
        values = list(self._values())
        sections: dict[str, list[EventDTO]] = {
            "trending": self.discover_trending(limit=per_section),
            "upcoming": self._dtos(filters.upcoming(values, now), per_section),
            "ai_events": self.browse_by_category("ai", limit=per_section),
            "hackathons": self.browse_by_category("hackathon", limit=per_section),
            "conferences": self.browse_by_category("conference", limit=per_section),
            "meetups": self.browse_by_category("meetup", limit=per_section),
            "workshops": self.browse_by_category("workshop", limit=per_section),
            "startup_events": self.browse_by_category("startup", limit=per_section),
            "developer_festivals": self._dtos(
                self._by_title(values, r"devfest|dev ?fest|developer festival", now), per_section
            ),
            "government_tech": self._dtos(
                self._by_title(values, r"\bgovern?ment\b|\bgovt\b|\bgov\b", now), per_section
            ),
            "university_events": self._dtos(
                self._by_title(values, r"university|college|campus|student", now), per_section
            ),
            "recently_added": self._dtos(filters.recently_added(values, now), per_section),
            "registration_closing": self.discover_registration_closing(limit=per_section),
            "online_events": self.discover_online(limit=per_section),
            "free_events": self.discover_free(limit=per_section),
        }
        if city:
            sections["nearby_events"] = self.discover_nearby(city, limit=per_section)
        if user_id:
            sections["recommended"] = [
                r.event for r in self.recommendations(user_id, limit=per_section)
            ]
        return HomepageDTO(sections=sections)

    def _by_title(self, events, pattern: str, now: datetime) -> list[StoredEvent]:
        regex = re.compile(pattern, re.IGNORECASE)
        return [s for s in filters.upcoming(events, now) if regex.search(s.event.title)]

    # --- event details ---

    def event_details(self, key: str) -> EventDetailDTO | None:
        stored = self._events.get(key)
        if stored is None:
            return None
        similar = [
            to_event_dto(self._events[k])
            for k, _ in self._similarity.similar_to(key, limit=6)
            if k in self._events
        ]
        return EventDetailDTO(
            event=to_event_dto(stored),
            ai=to_ai_dto(self._enrichment.get(key)),
            lifecycle=lifecycle_state(stored, self._now()).value,
            trending_score=self._trending.score(stored, self._now())[0],
            similar=similar,
            organizer=self._event_entity_profile(key, EdgeType.ORGANIZED_BY),
            community=self._event_entity_profile(key, EdgeType.HOSTED_BY),
            city=self._event_city_profile(key),
        )

    def _event_entity_profile(self, key: str, edge: EdgeType) -> EntityProfileDTO | None:
        neighbors = self._graph.neighbors(f"event:{key}", type=edge, direction="out")
        if not neighbors:
            return None
        profile = self._profiles_by_id.get(neighbors[0])
        return to_entity_profile_dto(profile) if profile else None

    def _event_city_profile(self, key: str) -> EntityProfileDTO | None:
        neighbors = self._graph.neighbors(f"event:{key}", type=EdgeType.IN_CITY, direction="out")
        if not neighbors:
            return None
        entity = self._graph.get_entity(neighbors[0])
        return self._city_dto(entity) if entity else None

    # --- similar events ---

    def similar_events(self, key: str, *, limit: int = 10) -> list[EventDTO]:
        return [
            to_event_dto(self._events[k])
            for k, _ in self._similarity.similar_to(key, limit=limit)
            if k in self._events
        ]

    # --- recommendations (delegates to User Intelligence) ---

    def record_interaction(self, interaction: Interaction) -> None:
        self._users.record_interaction(interaction)

    def recommendations(self, user_id: str, *, limit: int = 10) -> list[RecommendationDTO]:
        recs = self._users.recommend(user_id, now=self._now(), limit=limit)
        return [
            to_recommendation_dto(r, self._events[r.event_key])
            for r in recs
            if r.event_key in self._events
        ]

    # --- entity profiles ---

    def community_profile(self, name: str) -> EntityProfileDTO | None:
        return self._entity_profile(name, EntityType.COMMUNITY, EdgeType.ACTIVE_IN)

    def organizer_profile(self, name: str) -> EntityProfileDTO | None:
        return self._entity_profile(name, EntityType.ORGANIZATION, None)

    def series_profile(self, name: str) -> EntityProfileDTO | None:
        return self._entity_profile(name, EntityType.EVENT_SERIES, None)

    def _entity_profile(self, name, entity_type, chapter_edge) -> EntityProfileDTO | None:
        entity = self._entity_queries.find_entity(name, entity_type)
        if entity is None:
            return None
        profile = self._profiles_by_id.get(entity.id)
        if profile is None:
            return None
        extra: dict = {}
        if chapter_edge is not None:
            extra["chapters"] = self._graph.neighbors(entity.id, type=chapter_edge, direction="out")
        return to_entity_profile_dto(profile, extra=extra)

    def city_profile(self, name: str) -> EntityProfileDTO | None:
        entity = self._entity_queries.find_entity(name, EntityType.CITY)
        return self._city_dto(entity) if entity else None

    def _city_dto(self, entity) -> EntityProfileDTO:
        active = len(filters.by_city(self._values(), entity.name, self._now()))
        communities = self._graph.neighbors(entity.id, type=EdgeType.ACTIVE_IN, direction="in")
        return EntityProfileDTO(
            entity_type="city",
            name=entity.name,
            total_events=entity.event_count,
            active_events=active,
            extra={"communities": communities, "categories": sorted(entity.categories)},
        )

    # --- directory (read-only enumeration for entity index pages) ---

    def directory(self) -> dict[str, list[tuple[str, int]]]:
        """Top organizers / communities / series / cities (name, event count) — a read-only
        projection of the already-built profiles + graph, for browse/index pages."""

        def top(entity_type: str) -> list[tuple[str, int]]:
            rows = [
                (p.name, p.total_events)
                for p in self._profiles
                if p.entity_type == entity_type
            ]
            return sorted(rows, key=lambda kv: (-kv[1], kv[0]))[:24]

        cities = sorted(
            ((e.name, e.event_count) for e in self._graph.entities(EntityType.CITY)),
            key=lambda kv: (-kv[1], kv[0]),
        )[:24]
        return {
            "organizers": top("organization"),
            "communities": top("community"),
            "series": top("event_series"),
            "cities": cities,
        }

    # --- analytics (read-only) ---

    def analytics(self) -> AnalyticsDTO:
        counts = self._graph.counts()
        providers = {s.event.provider for s in self._values()}
        topics: Counter[str] = Counter(t for e in self._enrichment.values() for t in e.topics)
        techs: Counter[str] = Counter(t for e in self._enrichment.values() for t in e.technologies)
        community_profiles = [p for p in self._profiles if p.entity_type == "community"]
        top_communities = sorted(
            ((p.name, p.total_events) for p in community_profiles), key=lambda kv: (-kv[1], kv[0])
        )[:5]
        return AnalyticsDTO(
            total_events=len(self._events),
            cities=counts.get("city", 0),
            communities=counts.get("community", 0),
            organizers=counts.get("organization", 0),
            providers=len(providers),
            topics=len(topics),
            technologies=len(techs),
            top_topics=topics.most_common(5),
            top_technologies=techs.most_common(5),
            top_communities=top_communities,
        )
