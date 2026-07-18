"""AI Event Understanding — semantic enrichment of every event.

An additive, deterministic layer that turns a normalized event into an AI-understood object
(topics, technologies, skills, audiences, difficulty, careers, summary) stored **separately**
from the frozen Event model, plus event similarity. Interfaces are defined for future LLM
enrichment / embeddings / semantic search / recommendations / assistant — none implemented.
Modifies nothing frozen.
"""

from app.enrichment.enricher import DeterministicEnricher, Enricher
from app.enrichment.extractors import (
    career_relevance,
    detect_audiences,
    estimate_difficulty,
    extract_technologies,
    extract_topics,
    generate_summary,
    infer_skills,
)
from app.enrichment.models import Difficulty, EnrichmentMethod, EventEnrichment
from app.enrichment.pipeline import EnrichmentPipeline
from app.enrichment.similarity import EventSimilarity
from app.enrichment.store import EnrichmentStore, InMemoryEnrichmentStore

__all__ = [
    "EnrichmentPipeline",
    "DeterministicEnricher",
    "Enricher",
    "EventEnrichment",
    "Difficulty",
    "EnrichmentMethod",
    "EventSimilarity",
    "EnrichmentStore",
    "InMemoryEnrichmentStore",
    "extract_topics",
    "extract_technologies",
    "infer_skills",
    "detect_audiences",
    "estimate_difficulty",
    "career_relevance",
    "generate_summary",
]
