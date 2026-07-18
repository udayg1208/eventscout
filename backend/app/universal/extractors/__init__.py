"""The isolated extractor registry (Phase 10B), grouped into structural tiers for early-stop.

Tier 1 (structured, highest confidence) runs first; if it already yields a confident event the
engine can stop before the softer tiers. Each extractor is independent — order within a tier is
irrelevant because the merge step is deterministic.
"""

from __future__ import annotations

from app.universal.extractors.calendar import CalendarExtractor
from app.universal.extractors.hydration import (
    AstroExtractor,
    EmbeddedJsonExtractor,
    HydrationExtractor,
    NextDataExtractor,
    NuxtExtractor,
)
from app.universal.extractors.semantic import SemanticBlockExtractor
from app.universal.extractors.structured import (
    JsonLdExtractor,
    MicrodataExtractor,
    OpenGraphExtractor,
)
from app.universal.extractors.textual import (
    DefinitionListExtractor,
    FaqExtractor,
    MarkdownExtractor,
    TableExtractor,
)

# Tier 1: structured/serialized data (schema.org, hydration blobs, calendars) — strongest signal.
TIER_STRUCTURED = [
    JsonLdExtractor(),
    MicrodataExtractor(),
    NextDataExtractor(),
    NuxtExtractor(),
    AstroExtractor(),
    HydrationExtractor(),
    EmbeddedJsonExtractor(),
    CalendarExtractor(),
]
# Tier 2: semi-structured page furniture (OpenGraph, tables, definition lists).
TIER_SEMI = [
    OpenGraphExtractor(),
    TableExtractor(),
    DefinitionListExtractor(),
]
# Tier 3: prose / visual blocks (Markdown, FAQ, semantic cards) — softest, run last.
TIER_TEXTUAL = [
    MarkdownExtractor(),
    FaqExtractor(),
    SemanticBlockExtractor(),
]

EXTRACTION_TIERS = [TIER_STRUCTURED, TIER_SEMI, TIER_TEXTUAL]
ALL_EXTRACTORS = [e for tier in EXTRACTION_TIERS for e in tier]

__all__ = [
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
    "TIER_STRUCTURED",
    "TIER_SEMI",
    "TIER_TEXTUAL",
    "EXTRACTION_TIERS",
    "ALL_EXTRACTORS",
]
