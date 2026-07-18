"""Universal Event Understanding Engine (Phase 10B).

Given ANY public webpage — HTML, blog, university page, Notion, GitHub, Markdown, hydrated React/
Next.js/Vue/Astro, JSON-LD, calendar, RSS, FAQ, table — determine whether it contains real
technology/professional events and extract them with provenance, without caring about the
framework. The engine asks "where is the event information?", not "what framework is this?".
Additive; reuses D4's provenance model, D2's hydration extractors, D1's feed parsing, the 5A
taxonomy, and `city.detect_city`. No network, no browser, no LLM; discovery only — nothing is
written to the catalog.
"""

from __future__ import annotations

from app.universal.confidence import WEIGHTS, ConfidenceScore, UniversalConfidence
from app.universal.engine import UniversalEventEngine
from app.universal.extractors import (
    ALL_EXTRACTORS,
    EXTRACTION_TIERS,
    AstroExtractor,
    CalendarExtractor,
    DefinitionListExtractor,
    EmbeddedJsonExtractor,
    FaqExtractor,
    HydrationExtractor,
    JsonLdExtractor,
    MarkdownExtractor,
    MicrodataExtractor,
    NextDataExtractor,
    NuxtExtractor,
    OpenGraphExtractor,
    SemanticBlockExtractor,
    TableExtractor,
)
from app.universal.fingerprint import FingerprintStore, fingerprint
from app.universal.merge import merge_raw_events
from app.universal.models import (
    FIELD_NAMES,
    EventMode,
    EventType,
    ExtractedField,
    ExtractionResult,
    ExtractionSource,
    Page,
    Provenance,
    RawEvent,
    UniversalEvent,
    UniversalReport,
)
from app.universal.normalize import normalize
from app.universal.validator import UniversalValidator, ValidationResult

__all__ = [
    "UniversalEventEngine",
    "UniversalEvent",
    "UniversalReport",
    "Page",
    "ExtractionResult",
    "ExtractionSource",
    "RawEvent",
    "EventType",
    "EventMode",
    "FIELD_NAMES",
    "ExtractedField",
    "Provenance",
    "UniversalConfidence",
    "ConfidenceScore",
    "WEIGHTS",
    "UniversalValidator",
    "ValidationResult",
    "normalize",
    "merge_raw_events",
    "fingerprint",
    "FingerprintStore",
    "ALL_EXTRACTORS",
    "EXTRACTION_TIERS",
    "JsonLdExtractor",
    "OpenGraphExtractor",
    "MicrodataExtractor",
    "NextDataExtractor",
    "NuxtExtractor",
    "AstroExtractor",
    "HydrationExtractor",
    "EmbeddedJsonExtractor",
    "MarkdownExtractor",
    "TableExtractor",
    "DefinitionListExtractor",
    "FaqExtractor",
    "CalendarExtractor",
    "SemanticBlockExtractor",
]
