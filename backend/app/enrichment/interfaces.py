"""Future extension interfaces — defined, NOT implemented (per the spec).

These are the seams a later AI stack plugs into without changing the deterministic engine or
anything frozen. Nothing here is built in Phase 5A.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.enrichment.enricher import Enricher
from app.enrichment.models import EventEnrichment
from app.models.event import Event


class LLMEnricher(Enricher):
    """A future enricher backed by an LLM. Produces the same `EventEnrichment` shape, so it
    can replace or augment the deterministic enricher (e.g. as a validate→retry→fallback,
    honoring the project's AI-safety rule: refine, never fetch or fabricate)."""


class Embedder(ABC):
    """text/enrichment → vector, for semantic search + recommendations (future)."""

    @abstractmethod
    def embed(self, enrichment: EventEnrichment) -> Sequence[float]: ...


class SemanticSearchIndex(ABC):
    """ANN index over enrichment embeddings (future — feeds the Search Infrastructure's
    SemanticRetriever seam)."""

    @abstractmethod
    async def upsert(self, key: str, vector: Sequence[float]) -> None: ...

    @abstractmethod
    async def search(self, vector: Sequence[float], *, limit: int) -> list[tuple[str, float]]: ...


class Recommender(ABC):
    """Personalized recommendations from a user profile + enriched events (future)."""

    @abstractmethod
    def recommend(self, user_profile: dict, events: Sequence[Event]) -> list[str]: ...


class AIAssistant(ABC):
    """Conversational access over the enriched catalog (future)."""

    @abstractmethod
    async def answer(self, question: str) -> str: ...
