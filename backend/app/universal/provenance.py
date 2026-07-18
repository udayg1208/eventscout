"""Provenance helpers (Phase 10B) — build `ExtractedField`s that always cite their source.

Thin constructors over D4's `ExtractedField`/`Provenance` so every extractor produces provenance-
bearing fields without boilerplate. `known()` for a value read from a snippet, `inferred()` for a
value derived from evidence (e.g. country from a city). Never build a field without a snippet —
that is the whole point of the engine.
"""

from __future__ import annotations

from app.discovery.ai.models import (
    ExtractedField,
    ExtractionMethod,
    FieldStatus,
    Provenance,
)

_MAX_SNIPPET = 200


def known(
    value: object,
    *,
    snippet: str,
    reason: str,
    confidence: float,
    method: ExtractionMethod = ExtractionMethod.DETERMINISTIC,
) -> ExtractedField:
    """A field read verbatim (or parsed) from `snippet`."""
    return ExtractedField(
        value=value,
        status=FieldStatus.EXTRACTED,
        provenance=Provenance(
            source_snippet=" ".join(str(snippet).split())[:_MAX_SNIPPET],
            reason=reason,
            confidence=round(max(0.0, min(1.0, confidence)), 3),
            method=method,
        ),
    )


def inferred(
    value: object,
    *,
    snippet: str,
    reason: str,
    confidence: float,
    method: ExtractionMethod = ExtractionMethod.DETERMINISTIC,
) -> ExtractedField:
    """A field derived from evidence (not read verbatim) — status INFERRED."""
    return ExtractedField(
        value=value,
        status=FieldStatus.INFERRED,
        provenance=Provenance(
            source_snippet=" ".join(str(snippet).split())[:_MAX_SNIPPET],
            reason=reason,
            confidence=round(max(0.0, min(1.0, confidence)), 3),
            method=method,
        ),
    )
