"""Future optimization seams (Phase 8A) — INTERFACES ONLY, no implementations.

8A produces recommendations; it changes nothing. These abstractions mark where later phases would
*act* on those recommendations — feeding queries into a real search engine, generating queries
adaptively, or expanding the crawl autonomously. Each raises `NotImplementedError`; acting on
recommendations is Phase 8B and requires explicit approval.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.discovery.optimization.budget import BudgetPlan
from app.discovery.optimization.query_optimizer import QueryOptimization


class QueryApplier(ABC):
    """FUTURE (8B): apply query recommendations (retire/boost/create) to the real search layer."""

    @abstractmethod
    def apply(self, optimization: QueryOptimization) -> None:  # pragma: no cover
        raise NotImplementedError("applying query changes is Phase 8B — requires approval")


class AdaptiveQueryGenerator(ABC):
    """FUTURE (8B): generate new queries adaptively (beyond the deterministic gap templates)."""

    @abstractmethod
    def generate(self, seed_gaps: list) -> list[str]:  # pragma: no cover
        raise NotImplementedError("adaptive query generation is deferred (8B)")


class BudgetEnforcer(ABC):
    """FUTURE (8B): push a BudgetPlan into the real crawl scheduler (change crawl frequencies)."""

    @abstractmethod
    def enforce(self, plan: BudgetPlan) -> None:  # pragma: no cover
        raise NotImplementedError("enforcing crawl budgets is Phase 8B — requires approval")
