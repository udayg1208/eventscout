"""AI Discovery (Phase 6G / D4) — understand pages that D1/D2 can't, via AI extraction.

D1 (structured), D2 (framework/hydration), and D3 (search) leave one gap: pages that describe
events only in **prose** — no RSS/JSON-LD/ICS/sitemap, no framework payload. D4 fills it with an
AI extractor, but under strict rules: AI may extract/classify/summarize/identify signals and MUST
NEVER fabricate; every field carries provenance; insufficient evidence returns UNKNOWN.

Deterministic-first (AI only when structured extraction is not confident), mock-only (no Gemini/
OpenAI), and discovery-only: it produces Candidate Sources for the Discovery Inbox — never
ingesting events, creating providers, or writing to the catalog. Output stops at the inbox.
"""

from app.discovery.ai.classifier import AIClassifier, MockAIClassifier
from app.discovery.ai.confidence import compute_confidence, search_score_from_rank
from app.discovery.ai.extractor import (
    AIExtractor,
    ExtractionInput,
    MockAIExtractor,
    merge_extractions,
)
from app.discovery.ai.models import (
    AIClassification,
    AIExtraction,
    ClassLabel,
    ConfidenceComponent,
    DiscoveryConfidence,
    ExtractedField,
    ExtractionMethod,
    FieldStatus,
    Provenance,
    SourceClass,
    ValidationResult,
    unknown,
)
from app.discovery.ai.pipeline import (
    AIDiscoveryPipeline,
    AIDiscoveryReport,
    Decision,
    PipelineOutcome,
)
from app.discovery.ai.store import (
    AIExtractionRecord,
    AIExtractionStore,
    InMemoryAIExtractionStore,
    SQLiteAIExtractionStore,
)
from app.discovery.ai.validator import validate

__all__ = [
    # models
    "AIExtraction",
    "ExtractedField",
    "Provenance",
    "FieldStatus",
    "ExtractionMethod",
    "AIClassification",
    "ClassLabel",
    "SourceClass",
    "DiscoveryConfidence",
    "ConfidenceComponent",
    "ValidationResult",
    "unknown",
    # extractor / classifier
    "AIExtractor",
    "MockAIExtractor",
    "ExtractionInput",
    "merge_extractions",
    "AIClassifier",
    "MockAIClassifier",
    # confidence / validation
    "compute_confidence",
    "search_score_from_rank",
    "validate",
    # pipeline
    "AIDiscoveryPipeline",
    "AIDiscoveryReport",
    "PipelineOutcome",
    "Decision",
    # store
    "AIExtractionStore",
    "InMemoryAIExtractionStore",
    "SQLiteAIExtractionStore",
    "AIExtractionRecord",
]
