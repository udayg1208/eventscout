"""Growth Planner (Phase 10F) — decide what should run next.

Two jobs: (1) *refill* the queue with work from the freshness engine (stale entities → refresh
tasks) and the opportunity engine (growth opportunities → expansion/refresh tasks); (2) *select* the
single best task to run this cycle — the highest-priority eligible task whose resource budget can
afford it, gated by backlog (don't validate with no seeds, don't onboard with an empty inbox). Every
decision returns an explaining reason. Deterministic; no network.
"""

from __future__ import annotations

from app.growth.budget import GrowthBudgetEngine
from app.growth.models import GrowthOpportunity, GrowthTask, TaskKind
from app.growth.queue import GrowthQueue


class GrowthPlanner:
    def refill_queue(
        self,
        queue: GrowthQueue,
        *,
        run: int,
        freshness_tasks: list[GrowthTask] | None = None,
        opportunities: list[GrowthOpportunity] | None = None,
    ) -> int:
        """Fold freshness + opportunity work into the queue (deduped). Returns tasks added."""
        added = 0
        for task in freshness_tasks or []:
            if queue.enqueue(task, run=run) == "queued":
                added += 1
        for opp in opportunities or []:
            if queue.enqueue(opp.to_task(), run=run) == "queued":
                added += 1
        return added

    def select(
        self,
        queue: GrowthQueue,
        budget: GrowthBudgetEngine,
        run: int,
        *,
        has_seed_backlog: bool = True,
        has_onboarding_backlog: bool = True,
    ) -> tuple[GrowthTask | None, str]:
        """Pick the top eligible task that is affordable and unblocked by backlog."""
        for task in queue.eligible(run):
            if task.kind is TaskKind.VALIDATION and not has_seed_backlog:
                continue  # nothing to validate yet
            if task.kind is TaskKind.ONBOARDING and not has_onboarding_backlog:
                continue  # nothing waiting in the inbox
            if not budget.can_afford(task.resource, 1):
                continue  # resource exhausted this period
            return task, (
                f"selected {task.kind.value}(target={task.target}, priority={task.priority}); "
                f"{task.resource.value} budget left={budget.remaining(task.resource)}"
            )
        return None, "no eligible/affordable task — idle cycle"
