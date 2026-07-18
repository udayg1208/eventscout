"""Entity resolution — deterministic, no LLM.

Maps messy raw names ("Google LLC", "Google India", "GDG Bangalore", "Google Dev Group")
onto canonical entities. Three gates, most-precise first:

1. **Normalization** — lowercase, strip legal suffixes / punctuation / trailing geo.
2. **Curated aliases** — a small hand-maintained table for the well-known ecosystem players
   (high precision, zero false merges for the cases we know).
3. **Gated fuzzy match** — rapidfuzz against already-seen entities *of the same type*, above
   a conservative threshold, to catch spelling variants we didn't enumerate.

Conservative by design: a high fuzzy threshold favors false *splits* (two nodes for one
real entity) over false *merges* (collapsing distinct entities) — splits are safe and
fixable; merges corrupt the graph. See ENTITY_RESOLUTION.md.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from app.entities.models import EntityType

_LEGAL_SUFFIXES = re.compile(
    r"\b(llc|inc|inc\.|ltd|ltd\.|pvt|private|limited|corporation|corp|co|company|"
    r"foundation|technologies|technology|labs|systems)\b",
    re.I,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(raw: str) -> str:
    """Lowercase, drop legal suffixes and punctuation, collapse whitespace."""
    text = raw.casefold()
    text = _LEGAL_SUFFIXES.sub(" ", text)
    text = _NON_ALNUM.sub(" ", text)
    return " ".join(text.split())


# Curated aliases: normalized-alias -> (canonical slug, display name). High precision.
_ALIASES: dict[EntityType, dict[str, tuple[str, str]]] = {
    EntityType.ORGANIZATION: {
        "google": ("google", "Google"),
        "google india": ("google", "Google"),
        "google cloud": ("google", "Google"),
        "google ai": ("google", "Google"),
        "google developers": ("google", "Google"),
        "microsoft": ("microsoft", "Microsoft"),
        "microsoft india": ("microsoft", "Microsoft"),
        "amazon": ("amazon", "Amazon"),
        "aws": ("amazon", "Amazon"),
        "amazon web services": ("amazon", "Amazon"),
        "meta": ("meta", "Meta"),
        "facebook": ("meta", "Meta"),
    },
    EntityType.COMMUNITY: {
        "gdg": ("google-developer-groups", "Google Developer Groups"),
        "google developer groups": ("google-developer-groups", "Google Developer Groups"),
        "google developer group": ("google-developer-groups", "Google Developer Groups"),
        "google dev group": ("google-developer-groups", "Google Developer Groups"),
        "cncf": ("cncf", "CNCF"),
        "cloud native computing": ("cncf", "CNCF"),
        "foss united": ("foss-united", "FOSS United"),
        "hasgeek": ("hasgeek", "Hasgeek"),
        "pydata": ("pydata", "PyData"),
    },
}


class EntityResolver:
    """Stateful resolver: learns canonical entities as it resolves (deterministic given a
    stable input order)."""

    def __init__(self, *, fuzzy_threshold: float = 0.92) -> None:
        self._threshold = fuzzy_threshold
        # per type: normalized-name -> (id, display)
        self._seen: dict[EntityType, dict[str, tuple[str, str]]] = {}

    def resolve(self, raw: str, entity_type: EntityType) -> tuple[str, str] | None:
        """Return (entity_id, display_name) or None if the name is empty/unusable."""
        normalized = normalize_name(raw)
        if not normalized:
            return None

        curated = _ALIASES.get(entity_type, {})
        if normalized in curated:
            slug, display = curated[normalized]
            return self._register(entity_type, normalized, f"{entity_type.value}:{slug}", display)

        # A curated alias appearing as a whole phrase inside a longer name (e.g. "gdg
        # bangalore" -> GDG). Longest alias first so the most specific match wins.
        for alias in sorted(curated, key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                slug, display = curated[alias]
                entity_id = f"{entity_type.value}:{slug}"
                return self._register(entity_type, normalized, entity_id, display)

        seen = self._seen.setdefault(entity_type, {})
        if normalized in seen:
            return seen[normalized]

        # gated fuzzy against already-seen names of this type
        best_id, best_display, best_score = None, None, 0.0
        for other_norm, (other_id, other_display) in seen.items():
            score = fuzz.token_sort_ratio(normalized, other_norm) / 100.0
            if score > best_score:
                best_id, best_display, best_score = other_id, other_display, score
        if best_id is not None and best_score >= self._threshold:
            seen[normalized] = (best_id, best_display)
            return best_id, best_display

        slug = normalized.replace(" ", "-")
        return self._register(entity_type, normalized, f"{entity_type.value}:{slug}", raw.strip())

    def _register(
        self, entity_type: EntityType, normalized: str, entity_id: str, display: str
    ) -> tuple[str, str]:
        self._seen.setdefault(entity_type, {})[normalized] = (entity_id, display)
        return entity_id, display
