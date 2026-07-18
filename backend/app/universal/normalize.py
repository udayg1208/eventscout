"""Normalization (Phase 10B) — canonicalize merged fields without losing provenance.

Light, provenance-preserving cleanup applied after merge: collapse whitespace in text fields,
dedupe the technologies list, coerce `mode`/`event_type` to the canonical enum vocabulary, and
infer country from a known city/state when it is missing. Never fabricates — an unrecognised value
is left as-is, and a genuinely absent field stays absent (UNKNOWN preferred).
"""

from __future__ import annotations

from app.universal.models import EventMode, EventType, ExtractedField
from app.universal.provenance import inferred

_TYPE_ALIASES = {t.value: t.value for t in EventType}
_TYPE_ALIASES.update({"conf": "conference", "meet-up": "meetup", "meet up": "meetup"})
_MODE_VALUES = {m.value for m in EventMode}


def _retext(ef: ExtractedField) -> ExtractedField:
    if isinstance(ef.value, str):
        cleaned = " ".join(ef.value.split())
        if cleaned != ef.value:
            return ExtractedField(value=cleaned, status=ef.status, provenance=ef.provenance)
    return ef


def normalize(fields: dict[str, ExtractedField]) -> dict[str, ExtractedField]:
    out = dict(fields)

    for name in ("title", "organizer", "description", "venue", "city", "state", "country"):
        if name in out and out[name].is_known:
            out[name] = _retext(out[name])

    tech = out.get("technologies")
    if tech and isinstance(tech.value, list):
        deduped = sorted({str(t).strip() for t in tech.value if str(t).strip()})
        out["technologies"] = ExtractedField(deduped, tech.status, tech.provenance)

    et = out.get("event_type")
    if et and isinstance(et.value, str):
        canon = _TYPE_ALIASES.get(et.value.lower())
        if canon:
            out["event_type"] = ExtractedField(canon, et.status, et.provenance)

    md = out.get("mode")
    if md and isinstance(md.value, str) and md.value.lower() in _MODE_VALUES:
        out["mode"] = ExtractedField(md.value.lower(), md.status, md.provenance)

    if "country" not in out or not out["country"].is_known:
        loc = out.get("city") or out.get("state")
        if loc and loc.is_known:
            out["country"] = inferred(
                "India",
                snippet=str(loc.value),
                reason="country inferred from Indian city/state",
                confidence=0.6,
            )
    return out
