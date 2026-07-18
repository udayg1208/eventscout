"""Series detection (Phase 10C) — identify recurring event brands + cadence.

Recognises recurring series (DevFest, Build with AI, Hacktoberfest, Cloud Community Day, Google
Cloud Arcade, PyCon, FOSS Meetup, Monthly Meetup, Weekly Workshop, …) and the cadence each implies.
Cadence found explicitly in the text ("every month") overrides the series default. Deterministic.
"""

from __future__ import annotations

from app.organizers.models import Cadence
from app.organizers.taxonomy import SERIES_PATTERNS, detect_cadence_word


def detect_series(text: str) -> list[tuple[str, Cadence, str]]:
    """All recurring series present → (series name, cadence, matched snippet)."""
    out: list[tuple[str, Cadence, str]] = []
    seen: set[str] = set()
    override = detect_cadence_word(text)
    for name, pat, cadence in SERIES_PATTERNS:
        m = pat.search(text)
        if m and name not in seen:
            seen.add(name)
            cad = override[0] if override else cadence
            out.append((name, cad, m.group(0)))
    return out


def dominant_cadence(text: str, series: list[tuple[str, Cadence, str]]) -> Cadence:
    """The most frequent (or explicitly stated) cadence for an organizer."""
    word = detect_cadence_word(text)
    if word:
        return word[0]
    if not series:
        return Cadence.UNKNOWN
    counts: dict[Cadence, int] = {}
    for _name, cad, _snip in series:
        counts[cad] = counts.get(cad, 0) + 1
    return max(counts, key=lambda c: counts[c])
