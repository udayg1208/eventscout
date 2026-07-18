"""Deduplication (Phase 6F / D3) — collapse identical discovered pages.

Pure, stateless helpers. A search-discovered source's identity is its **normalized URL** (already
computed by the parser), so the same page surfaced by several different queries collapses to one
candidate — keeping the best (lowest-numbered) rank so provenance points at the strongest hit.
`by_domain` is a reporting helper (how many distinct domains were discovered).
"""

from __future__ import annotations

from collections.abc import Iterable

from app.discovery.search.parser import ParsedResult


def key_for(parsed: ParsedResult) -> str:
    """Dedup identity for a discovered source (the normalized URL)."""
    return parsed.url


def dedupe(results: Iterable[ParsedResult]) -> list[ParsedResult]:
    """Collapse identical URLs, keeping the occurrence with the strongest (lowest) rank.

    Stable: first-seen order is preserved; a later, better-ranked duplicate replaces the earlier
    row in place rather than reordering.
    """
    best: dict[str, ParsedResult] = {}
    order: list[str] = []
    for r in results:
        k = key_for(r)
        current = best.get(k)
        if current is None:
            best[k] = r
            order.append(k)
        elif r.rank and (not current.rank or r.rank < current.rank):
            best[k] = r
    return [best[k] for k in order]


def by_domain(results: Iterable[ParsedResult]) -> dict[str, int]:
    """Count distinct results per registrable domain (reporting only)."""
    counts: dict[str, int] = {}
    for r in results:
        counts[r.domain] = counts.get(r.domain, 0) + 1
    return counts
