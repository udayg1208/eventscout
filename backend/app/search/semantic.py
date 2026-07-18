"""Future Semantic Layer — interfaces only, NO implementation (per the approved design).

Defines the contracts a semantic engine will implement so it can be added to the Hybrid
Retriever later without touching the Query Planner's structure, the other retrievers,
ranking, or any public interface. Nothing here is built in Phase 4B.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.models.search import SearchQuery
from app.search.candidates import CandidateSet


class Embedder(ABC):
    """text -> vector. A future implementation wraps a local/hosted embedding model."""

    @abstractmethod
    def embed(self, text: str) -> Sequence[float]: ...


class VectorIndex(ABC):
    """Approximate-nearest-neighbour store over event embeddings (future: pgvector, etc.)."""

    @abstractmethod
    async def upsert(self, key: str, vector: Sequence[float]) -> None: ...

    @abstractmethod
    async def search(self, vector: Sequence[float], *, limit: int) -> list[tuple[str, float]]: ...


class SemanticRetriever(ABC):
    """A `Retriever` shaped for embeddings. Deliberately abstract in Phase 4B — the Query
    Planner never emits it yet, and the Hybrid Retriever simply won't receive it."""

    name = "semantic"

    @abstractmethod
    async def retrieve(self, query: SearchQuery, limit: int) -> CandidateSet: ...
