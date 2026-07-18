"""Ecosystem Expansion engine (Phase 10D) — organizer graph → new Discovery Seeds.

Runs every expander over every known organizer under a budget (max depth / branches / seeds /
confidence / cooldown), collapsing equivalent seeds into one Discovery Seed Graph. Incremental:
seeds accumulate across runs and a cooldown skips recently-expanded sources. The output is
`ExpansionSeed`s for discovery (10A/10B) to verify — never Event objects, never a catalog write.
"""

from __future__ import annotations

from app.ecosystem.dedup import canonical_target
from app.ecosystem.expanders import ALL_EXPANDERS, ExpansionContext
from app.ecosystem.models import (
    DEFAULT_BUDGET,
    ExpansionBudget,
    ExpansionReport,
    ExpansionSeed,
    RelationshipPath,
    SeedGraph,
    SeedKind,
)
from app.ecosystem.store import SeedStore
from app.organizers.models import OrganizerGraph, OrganizerProfile

# generative kinds that fan a family across cities — a generated sibling equal to a known organizer
# is redundant and skipped (similar-organizer / connected-resource may legitimately point at knowns)
_GENERATED = {SeedKind.CHAPTER_SIBLING, SeedKind.SERIES_INSTANCE}


class EcosystemExpansionEngine:
    def __init__(
        self,
        *,
        expanders=None,
        budget: ExpansionBudget = DEFAULT_BUDGET,
        store: SeedStore | None = None,
    ) -> None:
        self._expanders = expanders if expanders is not None else ALL_EXPANDERS
        self._budget = budget
        self._store = store
        self.seeds = SeedGraph()
        self._run = 0
        self._last_expanded: dict[str, int] = {}

    def expand(
        self,
        sources: dict[str, OrganizerProfile],
        graph: OrganizerGraph | None = None,
        *,
        budget: ExpansionBudget | None = None,
    ) -> ExpansionReport:
        budget = budget or self._budget
        graph = graph or OrganizerGraph()
        self._run += 1
        report = ExpansionReport()
        total = 0
        stop = False
        # a seed that names an already-known organizer is not a NEW ecosystem — skip it
        known_targets = {
            canonical_target(p.get("name")) for p in sources.values() if p.get("name")
        }
        for sid, profile in sources.items():
            if stop:
                break
            since = self._run - self._last_expanded.get(sid, -1_000_000)
            if budget.cooldown_runs and since <= budget.cooldown_runs:
                report.sources_skipped += 1
                continue
            self._last_expanded[sid] = self._run
            report.sources_expanded += 1
            ctx = ExpansionContext(
                source_id=sid,
                profile=profile,
                graph=graph,
                base_path=RelationshipPath(nodes=[profile.get("name") or sid]),
                peers=sources,
            )
            for expander in self._expanders:
                for seed in expander.expand(ctx, budget):
                    if seed.confidence < budget.min_confidence:
                        report.budget_stops += 1
                        continue
                    if seed.kind in _GENERATED and seed.target_key in known_targets:
                        continue  # a generated sibling that is already a known organizer
                    if total >= budget.max_seeds:
                        report.budget_stops += 1
                        stop = True
                        break
                    report.seeds_generated += 1
                    total += 1
                    if self.seeds.add(seed) == "merged":
                        report.seeds_merged += 1
                if stop:
                    break
        report.by_kind = self.seeds.by_kind()
        return report

    def expand_from(self, org_engine, *, budget: ExpansionBudget | None = None) -> ExpansionReport:
        """Convenience: pull profiles + graph from a 10C OrganizerIntelligenceEngine."""
        sources = {oid: org_engine.profile(oid) for oid in org_engine.organizer_ids()}
        sources = {k: v for k, v in sources.items() if v is not None}
        return self.expand(sources, org_engine.graph, budget=budget)

    def recommend(self, *, limit: int = 50, min_confidence: float = 0.0) -> list[ExpansionSeed]:
        return [s for s in self.seeds.all() if s.confidence >= min_confidence][:limit]

    async def persist(self) -> None:
        if self._store is not None:
            await self._store.save(self.seeds)

    async def load_from_store(self) -> bool:
        if self._store is None:
            return False
        g = await self._store.load()
        if g is None:
            return False
        self.seeds = g
        return True
