"""University understanding (Phase 10C) — recognise campus structures.

Detects the university name (IIT/NIT/IIIT/BITS/VIT/SRM/MUJ/… or "X University/College/Institute")
and the campus unit type (department, club, student chapter, innovation cell, incubator, centre of
excellence). Deterministic.
"""

from __future__ import annotations

import re

from app.organizers.models import NodeType
from app.organizers.taxonomy import UNIVERSITY_UNITS, is_university

# acronym + optional trailing place ("IIT Bombay", "NIT Trichy", "MUJ")
_ACRONYM = re.compile(r"\b(IIT|NIT|IIIT|BITS|VIT|SRM|MUJ|MIT|DTU|NSUT)\b(?:\s+([A-Z][a-z]+))?")
_NAMED = re.compile(
    r"\b([A-Z][\w&.]+(?:\s+[A-Z][\w&.]+){0,4}\s+(?:University|College|Institute of Technology))\b"
)


def detect_university_name(text: str) -> tuple[str, str] | None:
    m = _NAMED.search(text)
    if m:
        return m.group(1).strip(), m.group(0)
    m = _ACRONYM.search(text)
    if m:
        name = m.group(0).strip()
        return name, name
    return None


def detect_university_units(text: str) -> list[tuple[str, NodeType, str]]:
    out: list[tuple[str, NodeType, str]] = []
    seen: set[str] = set()
    for label, pat, ntype in UNIVERSITY_UNITS:
        m = pat.search(text)
        if m and label not in seen:
            seen.add(label)
            out.append((label, ntype, m.group(0)))
    return out


def looks_like_university(text: str) -> bool:
    return is_university(text)
