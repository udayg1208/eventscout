"""Ecosystem Expansion models (Phase 10D).

This phase expands outward from every known organizer / community / chapter / sponsor / venue /
series (the 10C Organizer Graph) to discover entirely new ecosystems. The output is **Discovery
Seeds** (`ExpansionSeed`), never Event objects — each seed is a new target to hand to discovery
(10A/10B), with the relationship path explaining *why* it exists, a provenance record, and an
explainable confidence. Additive; reuses D4 provenance + 10C graph; no network, no browser, no LLM;
discovery only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.discovery.ai.models import Provenance


class SeedKind(StrEnum):
    CHAPTER_SIBLING = "chapter_sibling"  # GDG Bangalore → GDG Delhi
    SERIES_INSTANCE = "series_instance"  # DevFest → DevFest Jaipur
    SPONSOR_PROGRAM = "sponsor_program"  # Google → Build with AI
    UNIVERSITY_UNIT = "university_unit"  # IIIT Delhi → ACM Chapter
    VENUE_UNIT = "venue_unit"  # a campus venue → its clubs
    SIMILAR_ORGANIZER = "similar_organizer"  # deterministic similarity
    CONNECTED_RESOURCE = "connected_resource"  # organizer → github/discord/feed/…


@dataclass
class RelationshipPath:
    """Why a seed exists — the chain of labels/relations from the source to the seed."""

    nodes: list[str] = field(default_factory=list)  # ["GDG Bangalore", "Google", "Build with AI"]
    relations: list[str] = field(default_factory=list)  # ["sponsors", "runs_program"]

    @property
    def depth(self) -> int:
        return max(0, len(self.nodes) - 1)

    def extend(self, relation: str, node: str) -> RelationshipPath:
        return RelationshipPath(nodes=[*self.nodes, node], relations=[*self.relations, relation])

    def render(self) -> str:
        if not self.nodes:
            return ""
        out = self.nodes[0]
        for rel, node in zip(self.relations, self.nodes[1:], strict=False):
            out += f" --[{rel}]--> {node}"
        return out

    def as_dict(self) -> dict:
        return {"nodes": list(self.nodes), "relations": list(self.relations), "depth": self.depth}


@dataclass
class ExpansionSeed:
    kind: SeedKind
    target: str  # human name of the new thing to discover ("GDG Delhi")
    target_key: str  # canonical dedup key
    source: str  # origin organizer/node id
    reason: str
    confidence: float = 0.0
    confidence_breakdown: dict[str, float] = field(default_factory=dict)
    provenance: Provenance | None = None
    path: RelationshipPath = field(default_factory=RelationshipPath)
    search_hint: str | None = None
    alt_paths: list[RelationshipPath] = field(default_factory=list)  # equivalent paths (dedup)

    def dedup_key(self) -> tuple[str, str]:
        return (self.kind.value, self.target_key)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "target": self.target,
            "target_key": self.target_key,
            "source": self.source,
            "reason": self.reason,
            "confidence": round(self.confidence, 4),
            "confidence_breakdown": {k: round(v, 4) for k, v in self.confidence_breakdown.items()},
            "provenance": self.provenance.reason if self.provenance else None,
            "path": self.path.render(),
            "search_hint": self.search_hint,
            "alt_paths": len(self.alt_paths),
        }


@dataclass
class ExpansionBudget:
    """Prevents graph explosion — the traversal governor."""

    max_depth: int = 3
    max_branches: int = 8  # seeds per expander per source
    max_seeds: int = 200  # total seeds per run
    min_confidence: float = 0.2
    cooldown_runs: int = 0  # skip a source re-expanded within this many runs (incremental)

    def as_dict(self) -> dict:
        return {
            "max_depth": self.max_depth,
            "max_branches": self.max_branches,
            "max_seeds": self.max_seeds,
            "min_confidence": self.min_confidence,
            "cooldown_runs": self.cooldown_runs,
        }


DEFAULT_BUDGET = ExpansionBudget()


@dataclass
class SeedGraph:
    """The Discovery Seed Graph — deduped seeds keyed by (kind, canonical target)."""

    seeds: dict[tuple[str, str], ExpansionSeed] = field(default_factory=dict)

    def add(self, seed: ExpansionSeed) -> str:
        """Add or collapse a seed. Returns 'added' | 'merged'."""
        key = seed.dedup_key()
        existing = self.seeds.get(key)
        if existing is None:
            self.seeds[key] = seed
            return "added"
        # collapse equivalent expansion paths — keep strongest, record the alternate path
        if seed.path.render() != existing.path.render():
            existing.alt_paths.append(seed.path)
        if seed.confidence > existing.confidence:
            existing.confidence = seed.confidence
            existing.confidence_breakdown = seed.confidence_breakdown
            existing.reason = seed.reason
        return "merged"

    def all(self) -> list[ExpansionSeed]:
        return sorted(self.seeds.values(), key=lambda s: (-s.confidence, s.target))

    def by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.seeds.values():
            counts[s.kind.value] = counts.get(s.kind.value, 0) + 1
        return counts

    def as_dict(self) -> dict:
        return {
            "count": len(self.seeds),
            "by_kind": self.by_kind(),
            "seeds": [s.as_dict() for s in self.all()],
        }


@dataclass
class ExpansionReport:
    sources_expanded: int = 0
    sources_skipped: int = 0  # cooldown
    seeds_generated: int = 0  # before dedup
    seeds_merged: int = 0  # collapsed duplicates
    budget_stops: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "sources_expanded": self.sources_expanded,
            "sources_skipped": self.sources_skipped,
            "seeds_generated": self.seeds_generated,
            "seeds_merged": self.seeds_merged,
            "unique_seeds": self.seeds_generated - self.seeds_merged,
            "budget_stops": self.budget_stops,
            "by_kind": dict(self.by_kind),
        }
