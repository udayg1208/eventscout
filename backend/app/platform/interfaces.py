"""Future platform surfaces — interfaces only, no implementation.

Phase 6A ships one concrete surface: the in-process `PlatformService` facade returning DTOs.
Every *other* way the platform will eventually be consumed — mobile app, public REST API,
GraphQL, partner API, AI assistant, calendar sync, voice assistant — is declared here as an
interface so the shape is committed without prematurely building transport/auth/deployment.

Each is a thin adapter over `PlatformService`: it re-expresses the same DTOs in a different
protocol. None adds business logic. When any is implemented later it depends on the facade,
not on the internal engines — exactly as the frontend and HTTP API already do.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.platform.dto import (
    AnalyticsDTO,
    EntityProfileDTO,
    EventDetailDTO,
    EventDTO,
    HomepageDTO,
    RecommendationDTO,
)


class MobileApp(ABC):
    """Mobile backend-for-frontend: the same homepage/browse/detail DTOs, shaped for a
    bandwidth-constrained client (thinner payloads, cursor paging, offline hints)."""

    @abstractmethod
    def homepage(self, *, user_id: str | None, city: str | None) -> HomepageDTO: ...

    @abstractmethod
    def event(self, key: str) -> EventDetailDTO | None: ...


class PublicAPI(ABC):
    """Versioned public REST surface (`/v1/...`). Wraps facade methods with pagination,
    rate-limit metadata, and stable serialization of the existing DTOs."""

    @abstractmethod
    def list_events(self, *, cursor: str | None, limit: int) -> list[EventDTO]: ...

    @abstractmethod
    def analytics(self) -> AnalyticsDTO: ...


class GraphQLSchema(ABC):
    """GraphQL resolvers backed by the facade. Types mirror the DTOs; resolvers call the
    same orchestration methods — a client selects fields, the platform still owns the data."""

    @abstractmethod
    def resolve_event(self, key: str) -> EventDetailDTO | None: ...

    @abstractmethod
    def resolve_recommendations(self, user_id: str, limit: int) -> list[RecommendationDTO]: ...


class PartnerAPI(ABC):
    """Scoped feed for partners/aggregators — curated slices (by city, by organizer) of the
    public DTOs, with per-partner quotas. Read-only projection, never internal models."""

    @abstractmethod
    def feed(self, partner_id: str, *, city: str | None) -> list[EventDTO]: ...

    @abstractmethod
    def organizer(self, name: str) -> EntityProfileDTO | None: ...


class AIAssistant(ABC):
    """Conversational discovery. Turns a natural-language turn into facade calls (search,
    recommend, details) and narrates DTOs back. The LLM plans; the platform stays the source
    of truth (extends Phase-5A/5B assistant interfaces)."""

    @abstractmethod
    def ask(self, user_id: str | None, message: str) -> list[EventDTO]: ...


class CalendarIntegration(ABC):
    """Export events/recommendations to iCal/Google Calendar. Reads DTOs, emits calendar
    entries — a formatting adapter, no scheduling logic of its own."""

    @abstractmethod
    def export(self, keys: list[str]) -> bytes: ...


class VoiceAssistant(ABC):
    """Voice front-end (Alexa/Assistant skill). Same facade calls as `AIAssistant`, rendered
    as speech; returns a short spoken-friendly list of DTOs."""

    @abstractmethod
    def handle(self, user_id: str | None, utterance: str) -> list[EventDTO]: ...
