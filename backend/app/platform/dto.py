"""API DTO layer — the public response shapes.

The platform NEVER exposes internal models (`Event`, `StoredEvent`, `EventEnrichment`,
`OrganizerProfile`, …). These frozen DTOs are the only thing that crosses the platform
boundary; mappers convert internal → DTO. That keeps the public contract stable while the
internals evolve.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.enrichment.models import EventEnrichment
from app.intelligence.models import OrganizerProfile
from app.storage.models import StoredEvent
from app.users.models import Recommendation


@dataclass(frozen=True)
class EventDTO:
    key: str
    title: str
    url: str
    category: str
    start_date: str
    end_date: str | None
    city: str | None
    is_online: bool
    is_free: bool | None
    price: str | None
    provider: str
    description: str | None


@dataclass(frozen=True)
class AIMetadataDTO:
    topics: list[str]
    technologies: list[str]
    skills: list[str]
    audiences: list[str]
    difficulty: str
    careers: list[str]
    summary: str


@dataclass(frozen=True)
class EntityProfileDTO:
    entity_type: str  # organization | community | event_series | city
    name: str
    total_events: int
    active_events: int
    cities: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)  # chapters / editions / communities / quality


@dataclass(frozen=True)
class EventDetailDTO:
    event: EventDTO
    ai: AIMetadataDTO | None
    lifecycle: str
    trending_score: float
    similar: list[EventDTO]
    organizer: EntityProfileDTO | None
    community: EntityProfileDTO | None
    city: EntityProfileDTO | None


@dataclass(frozen=True)
class RecommendationDTO:
    event: EventDTO
    score: float
    reasons: list[str]


@dataclass(frozen=True)
class HomepageDTO:
    sections: dict[str, list[EventDTO]]


@dataclass(frozen=True)
class AnalyticsDTO:
    total_events: int
    cities: int
    communities: int
    organizers: int
    providers: int
    topics: int
    technologies: int
    top_topics: list[tuple[str, int]]
    top_technologies: list[tuple[str, int]]
    top_communities: list[tuple[str, int]]


# --------------------------- mappers (internal → DTO) ---------------------------


def to_event_dto(stored: StoredEvent) -> EventDTO:
    e = stored.event
    return EventDTO(
        key=stored.key,
        title=e.title,
        url=str(e.url),
        category=e.category.value,
        start_date=e.start_date.isoformat(),
        end_date=e.end_date.isoformat() if e.end_date else None,
        city=e.city,
        is_online=e.is_online,
        is_free=e.is_free,
        price=e.price,
        provider=e.provider,
        description=e.description,
    )


def to_ai_dto(enrichment: EventEnrichment | None) -> AIMetadataDTO | None:
    if enrichment is None:
        return None
    return AIMetadataDTO(
        topics=list(enrichment.topics),
        technologies=list(enrichment.technologies),
        skills=list(enrichment.skills),
        audiences=list(enrichment.audiences),
        difficulty=enrichment.difficulty.value,
        careers=list(enrichment.careers),
        summary=enrichment.summary,
    )


def to_entity_profile_dto(
    profile: OrganizerProfile, *, extra: dict | None = None
) -> EntityProfileDTO:
    return EntityProfileDTO(
        entity_type=profile.entity_type,
        name=profile.name,
        total_events=profile.total_events,
        active_events=profile.active_events,
        cities=list(profile.cities),
        extra={"average_quality": profile.average_quality, **(extra or {})},
    )


def to_recommendation_dto(recommendation: Recommendation, stored: StoredEvent) -> RecommendationDTO:
    return RecommendationDTO(
        event=to_event_dto(stored),
        score=recommendation.score,
        reasons=list(recommendation.reasons),
    )
