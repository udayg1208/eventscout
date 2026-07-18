"""Organizer identity resolution (Phase 10C) — merge the many surface forms of one organizer.

"GDG Bangalore", "Google Developer Group Bangalore", "Google Developers Group Bangalore" are one
organizer; "IEEE MUJ", "IEEE Student Branch MUJ", "IEEE MUJ SB" are one. Canonicalization expands
known abbreviations (GDG → Google Developer Group, SB → Student Branch, UG → User Group),
singularizes common plurals, drops identity-neutral filler (student, branch, group, chapter, …),
and reduces the name to an order-independent set of distinctive tokens. Two names with the same
token set are the same organizer. Deterministic; no fuzzy ML.
"""

from __future__ import annotations

import re

_ABBREV = {
    "gdg": "google developer group",
    "gdgs": "google developer group",
    "gdsc": "google developer student club",
    "gdscs": "google developer student club",
    "dsc": "developer student club",
    "sb": "student branch",
    "ug": "user group",
    "tfug": "tensorflow user group",
    "coe": "center of excellence",
    "k8s": "kubernetes",
    "pug": "python user group",
    "lug": "linux user group",
    "csi": "computer society of india",
    "ecell": "entrepreneurship cell",
    "icell": "innovation cell",
    "awsug": "aws user group",
}
_PLURAL = {
    "developers": "developer",
    "groups": "group",
    "clubs": "club",
    "chapters": "chapter",
    "societies": "society",
    "communities": "community",
    "labs": "lab",
    "branches": "branch",
}
# tokens that never change organizer identity (roles/qualifiers/stopwords)
_FILLER = {
    "the",
    "of",
    "for",
    "and",
    "a",
    "an",
    "student",
    "branch",
    "chapter",
    "group",
    "club",
    "society",
    "user",
    "community",
    "official",
    "presents",
    "by",
    "at",
    "in",
}
_PUNCT = re.compile(r"[^\w\s]")


def _tokens(name: str) -> list[str]:
    text = _PUNCT.sub(" ", name.lower())
    out: list[str] = []
    for tok in text.split():
        expanded = _ABBREV.get(tok, tok)
        for t in expanded.split():
            out.append(_PLURAL.get(t, t))
    return out


def canonical_tokens(name: str) -> frozenset[str]:
    """The order-independent set of identity-bearing tokens."""
    return frozenset(t for t in _tokens(name) if t not in _FILLER)


def canonical_key(name: str) -> str:
    """A stable identity key — same for every alias of the same organizer."""
    return " ".join(sorted(canonical_tokens(name)))


def is_same_organizer(a: str, b: str, *, threshold: float = 0.6) -> bool:
    ta, tb = canonical_tokens(a), canonical_tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    inter, union = len(ta & tb), len(ta | tb)
    return bool(union) and inter / union >= threshold


def resolve_aliases(names: list[str]) -> dict[str, list[str]]:
    """Group surface names by canonical key → sorted surface forms (identity resolution)."""
    groups: dict[str, set[str]] = {}
    for n in names:
        key = canonical_key(n)
        if key:
            groups.setdefault(key, set()).add(n.strip())
    return {k: sorted(v) for k, v in groups.items()}
