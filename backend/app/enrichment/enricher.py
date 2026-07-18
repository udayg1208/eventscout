"""Enricher — turns an event into an `EventEnrichment`.

`Enricher` is the abstraction (so a future `LLMEnricher` slots in — see `interfaces.py`);
`DeterministicEnricher` is the rule-based implementation used today. Given the same event it
always produces the same enrichment.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.enrichment.extractors import (
    career_relevance,
    detect_audiences,
    estimate_difficulty,
    extract_technologies,
    extract_topics,
    generate_summary,
    infer_skills,
)
from app.enrichment.models import EnrichmentMethod, EventEnrichment
from app.models.event import Event


class Enricher(ABC):
    @abstractmethod
    def enrich(self, key: str, event: Event) -> EventEnrichment:
        """Produce the semantic understanding for one event."""


class DeterministicEnricher(Enricher):
    def enrich(self, key: str, event: Event) -> EventEnrichment:
        topics = extract_topics(event)
        technologies = extract_technologies(event)
        difficulty = estimate_difficulty(event)
        skills = infer_skills(event, topics)
        audiences = detect_audiences(event, topics, difficulty)
        careers = career_relevance(topics)
        summary = generate_summary(
            event,
            topics=topics,
            technologies=technologies,
            audiences=audiences,
            difficulty=difficulty,
        )
        return EventEnrichment(
            key=key,
            topics=topics,
            technologies=technologies,
            skills=skills,
            audiences=audiences,
            difficulty=difficulty,
            careers=careers,
            summary=summary,
            method=EnrichmentMethod.DETERMINISTIC,
        )
