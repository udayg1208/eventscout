"""Duplicate resolution (Phase 10D) — collapse equivalent expansion paths.

The same new ecosystem is often reached by several routes (GDG Delhi via chapter-sibling *and* via
a DevFest series instance). Seeds are keyed by (kind, canonical target) — reusing 10C's identity
canonicalization — so equivalents collapse into one seed, keeping the strongest confidence and
recording the alternate paths. Deterministic.
"""

from __future__ import annotations

from app.ecosystem.models import ExpansionSeed, SeedGraph
from app.organizers.identity import canonical_key


def canonical_target(name: str) -> str:
    """The dedup key for a seed target — same organizer identity → same key."""
    return canonical_key(name)


class SeedDeduplicator:
    def dedupe(self, seeds: list[ExpansionSeed]) -> list[ExpansionSeed]:
        graph = SeedGraph()
        for s in seeds:
            graph.add(s)
        return graph.all()

    @staticmethod
    def merged_count(seeds: list[ExpansionSeed]) -> int:
        graph = SeedGraph()
        merged = 0
        for s in seeds:
            if graph.add(s) == "merged":
                merged += 1
        return merged
