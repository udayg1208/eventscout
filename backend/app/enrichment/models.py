"""AI enrichment models — the semantic understanding attached to each event.

`EventEnrichment` is stored **separately** from the frozen `Event` (keyed by the event key),
so the Event model is never modified and a future Opportunity model can consume it directly.
Deterministic today; the `method` field records provenance so LLM-produced enrichment can
coexist later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class EnrichmentMethod(StrEnum):
    DETERMINISTIC = "deterministic"
    LLM = "llm"  # future


@dataclass(frozen=True)
class EventEnrichment:
    """The AI-understood view of one event (references the event by key; no event body)."""

    key: str
    topics: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    audiences: list[str] = field(default_factory=list)
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    careers: list[str] = field(default_factory=list)
    summary: str = ""
    method: EnrichmentMethod = EnrichmentMethod.DETERMINISTIC

    def feature_set(self) -> set[str]:
        """A namespaced feature bag used for similarity (topics/tech/skills)."""
        return (
            {f"topic:{t}" for t in self.topics}
            | {f"tech:{t}" for t in self.technologies}
            | {f"skill:{s}" for s in self.skills}
        )
