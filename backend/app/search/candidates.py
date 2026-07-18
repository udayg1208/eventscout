"""CandidateSet — the common currency of retrieval.

Retrievers return candidates as **event keys + a retrieval score + the source retriever**,
never `Event` objects. Events are loaded from the Repository only *after* fusion, so
retrieval stays cheap and index-bounded. Metadata is an optional per-candidate bag for
future signals (e.g. matched fields, entity name).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Candidate:
    event_key: str
    score: float  # retriever-local relevance (higher = better)
    source: str  # the retriever that produced it
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateSet:
    """An ordered (best-first) set of candidates from one retriever."""

    source: str
    candidates: list[Candidate] = field(default_factory=list)

    def keys(self) -> list[str]:
        return [c.event_key for c in self.candidates]

    def __len__(self) -> int:
        return len(self.candidates)

    def __iter__(self) -> Iterable[Candidate]:
        return iter(self.candidates)

    @classmethod
    def empty(cls, source: str) -> CandidateSet:
        return cls(source=source, candidates=[])
