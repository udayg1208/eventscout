"""Chapter detection (Phase 10C) — recognise the big recurring community families.

Matches an organizer name/text against the known chapter families (GDG, GDSC, IEEE, ACM, CSI,
Mozilla, AWS UG, Kubernetes, PyData, PyLadies, TFUG, React, Rust, Linux, Cloud Native, FOSS United,
…) and returns the family plus the node type it implies (chapter / student chapter / professional
society). Deterministic.
"""

from __future__ import annotations

from app.organizers.models import NodeType
from app.organizers.taxonomy import CHAPTER_FAMILIES


def detect_chapter(text: str) -> tuple[str, str, NodeType, str] | None:
    """(family key, canonical full name, node type, matched snippet) or None."""
    for key, full, pat, ntype in CHAPTER_FAMILIES:
        m = pat.search(text)
        if m:
            return key, full, ntype, m.group(0)
    return None


def all_chapters(text: str) -> list[tuple[str, str, NodeType, str]]:
    out: list[tuple[str, str, NodeType, str]] = []
    for key, full, pat, ntype in CHAPTER_FAMILIES:
        m = pat.search(text)
        if m:
            out.append((key, full, ntype, m.group(0)))
    return out
