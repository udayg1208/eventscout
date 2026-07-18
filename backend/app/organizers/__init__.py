"""Organizer & Community Intelligence Engine (Phase 10C).

Discovers the organizers, communities, chapters, series and recurring ecosystems that continuously
generate events — the Organizer Graph, not Event objects. Once one organizer is found, its
ecosystem (chapter parent, university, series, sponsors, calendars, feeds, social channels) is
expanded automatically. Additive; reuses D4 provenance + 10B text helpers; no network, no browser,
no LLM; discovery only — nothing is written to the catalog.
"""

from __future__ import annotations

from app.organizers.chapters import all_chapters, detect_chapter
from app.organizers.confidence import OrganizerConfidence, OrganizerConfidenceScore
from app.organizers.engine import OrganizerIntelligenceEngine
from app.organizers.extract import OrganizerExtractor
from app.organizers.health import classify_health
from app.organizers.identity import (
    canonical_key,
    canonical_tokens,
    is_same_organizer,
    resolve_aliases,
)
from app.organizers.models import (
    ORGANIZER_FIELDS,
    Cadence,
    Edge,
    Health,
    Node,
    NodeType,
    OrganizerGraph,
    OrganizerProfile,
    RelationType,
    cadence_days,
)
from app.organizers.prediction import Opportunity, predict_opportunity
from app.organizers.relationships import RelationshipDiscoverer
from app.organizers.series import detect_series, dominant_cadence
from app.organizers.similarity import CommunitySimilarity, SimilarityScore
from app.organizers.store import GraphStore, InMemoryGraphStore, SQLiteGraphStore
from app.organizers.university import detect_university_name, detect_university_units

__all__ = [
    "OrganizerIntelligenceEngine",
    "OrganizerExtractor",
    "OrganizerProfile",
    "OrganizerGraph",
    "Node",
    "Edge",
    "NodeType",
    "RelationType",
    "Health",
    "Cadence",
    "ORGANIZER_FIELDS",
    "cadence_days",
    "canonical_key",
    "canonical_tokens",
    "is_same_organizer",
    "resolve_aliases",
    "detect_chapter",
    "all_chapters",
    "detect_series",
    "dominant_cadence",
    "detect_university_name",
    "detect_university_units",
    "CommunitySimilarity",
    "SimilarityScore",
    "OrganizerConfidence",
    "OrganizerConfidenceScore",
    "classify_health",
    "predict_opportunity",
    "Opportunity",
    "RelationshipDiscoverer",
    "GraphStore",
    "InMemoryGraphStore",
    "SQLiteGraphStore",
]
