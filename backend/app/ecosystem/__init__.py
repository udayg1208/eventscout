"""Ecosystem Expansion Engine (Phase 10D).

Expands outward from every known organizer / community / chapter / sponsor / venue / recurring
series (the 10C Organizer Graph) to discover entirely new ecosystems, emitting **Discovery Seeds**
— new targets for discovery (10A/10B) to verify — never Event objects. Each seed carries the
relationship path that explains why it exists, an explainable confidence, and provenance. Additive;
reuses 10C's graph + identity + similarity and D4 provenance; no network, no browser, no LLM;
discovery only.
"""

from __future__ import annotations

from app.ecosystem.confidence import ExpansionConfidence, ExpansionConfidenceScore
from app.ecosystem.dedup import SeedDeduplicator, canonical_target
from app.ecosystem.engine import EcosystemExpansionEngine
from app.ecosystem.expanders import (
    ALL_EXPANDERS,
    ChapterExpander,
    ConnectedResourceExpander,
    ExpansionContext,
    SeriesExpander,
    SimilarOrganizerExpander,
    SponsorExpander,
    UniversityExpander,
    VenueExpander,
)
from app.ecosystem.models import (
    DEFAULT_BUDGET,
    ExpansionBudget,
    ExpansionReport,
    ExpansionSeed,
    RelationshipPath,
    SeedGraph,
    SeedKind,
)
from app.ecosystem.store import InMemorySeedStore, SeedStore, SQLiteSeedStore

__all__ = [
    "EcosystemExpansionEngine",
    "ExpansionSeed",
    "SeedKind",
    "RelationshipPath",
    "ExpansionBudget",
    "DEFAULT_BUDGET",
    "SeedGraph",
    "ExpansionReport",
    "ExpansionContext",
    "ExpansionConfidence",
    "ExpansionConfidenceScore",
    "SeedDeduplicator",
    "canonical_target",
    "ChapterExpander",
    "SeriesExpander",
    "SponsorExpander",
    "UniversityExpander",
    "VenueExpander",
    "SimilarOrganizerExpander",
    "ConnectedResourceExpander",
    "ALL_EXPANDERS",
    "SeedStore",
    "InMemorySeedStore",
    "SQLiteSeedStore",
]
