"""The discovery pipeline as data (Phase 9A).

The canonical loop — Search → Web → Expansion → Social → Rendered → Inbox → Onboarding → Ops →
Catalog Refresh → Optimization → repeat — is expressed as a list of `StageSpec`s with schedules,
priorities, budgets, and seed-flow edges (`produces_for`). The planner reads this data; it hardcodes
no order. Reorder, disable, reprioritise, or reschedule a stage by editing the spec — the control
plane adapts. `Pipeline` also exposes the seed-flow edges so a stage's produced seeds fan out to the
right downstream backlogs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.orchestrator.models import (
    BudgetKind,
    Schedule,
    ScheduleKind,
    StageName,
    StageSpec,
    Trigger,
)


def default_pipeline() -> list[StageSpec]:
    """The default EventScout discovery pipeline. Priorities set the canonical order; triggers +
    seed-flow make it event-driven, not a fixed sequence."""
    B = BudgetKind
    return [
        StageSpec(
            name=StageName.SEARCH_DISCOVERY,
            schedule=Schedule(kind=ScheduleKind.HOURLY),
            priority=9.0,
            trigger=Trigger.SCHEDULE,
            budgets={B.SEARCH: 20, B.PAGE: 50},
            produces_for=[StageName.WEB_DISCOVERY, StageName.EXPANSION],
        ),
        StageSpec(
            name=StageName.WEB_DISCOVERY,
            schedule=Schedule(kind=ScheduleKind.HOURLY),
            priority=8.5,
            trigger=Trigger.BOTH,
            budgets={B.SEARCH: 20, B.PAGE: 100},
            produces_for=[StageName.EXPANSION, StageName.RENDERED_DISCOVERY],
        ),
        StageSpec(
            name=StageName.EXPANSION,
            schedule=Schedule(kind=ScheduleKind.CONTINUOUS),
            priority=8.0,
            trigger=Trigger.BACKLOG,
            budgets={B.CRAWL: 200, B.PAGE: 200, B.DEPTH: 3},
            produces_for=[
                StageName.SOCIAL_DISCOVERY,
                StageName.RENDERED_DISCOVERY,
                StageName.INBOX,
            ],
        ),
        StageSpec(
            name=StageName.SOCIAL_DISCOVERY,
            schedule=Schedule(kind=ScheduleKind.CONTINUOUS),
            priority=7.0,
            trigger=Trigger.BACKLOG,
            budgets={B.PAGE: 100},
            produces_for=[StageName.INBOX],
        ),
        StageSpec(
            name=StageName.RENDERED_DISCOVERY,
            schedule=Schedule(kind=ScheduleKind.CONTINUOUS),
            priority=7.0,
            trigger=Trigger.BACKLOG,
            budgets={B.PAGE: 100, B.AI: 50},
            produces_for=[StageName.INBOX],
        ),
        StageSpec(
            name=StageName.INBOX,
            schedule=Schedule(kind=ScheduleKind.CONTINUOUS),
            priority=6.0,
            trigger=Trigger.BACKLOG,
            budgets={},
            produces_for=[StageName.ONBOARDING],
        ),
        StageSpec(
            name=StageName.ONBOARDING,
            schedule=Schedule(kind=ScheduleKind.CONTINUOUS),
            priority=5.0,
            trigger=Trigger.BACKLOG,
            budgets={B.AI: 50, B.PROVIDER: 10},
            produces_for=[StageName.PRODUCTION_OPS],
        ),
        StageSpec(
            name=StageName.PRODUCTION_OPS,
            schedule=Schedule(kind=ScheduleKind.CONTINUOUS),
            priority=4.5,
            trigger=Trigger.BACKLOG,
            budgets={B.PROVIDER: 10},
            produces_for=[StageName.CATALOG_REFRESH],
        ),
        StageSpec(
            name=StageName.CATALOG_REFRESH,
            schedule=Schedule(kind=ScheduleKind.DAILY),
            priority=4.0,
            trigger=Trigger.BOTH,
            budgets={},
            produces_for=[],
        ),
        StageSpec(
            name=StageName.OPTIMIZATION,
            schedule=Schedule(kind=ScheduleKind.DAILY),
            priority=3.0,
            trigger=Trigger.SCHEDULE,
            budgets={B.AI: 20},
            produces_for=[StageName.SEARCH_DISCOVERY],  # feeds better seeds/queries back to the top
        ),
    ]


@dataclass
class Pipeline:
    """A configured pipeline: the stage specs + fast lookups + seed-flow edges."""

    specs: list[StageSpec] = field(default_factory=default_pipeline)

    def __post_init__(self) -> None:
        self._by_name = {s.name: s for s in self.specs}

    def names(self) -> list[StageName]:
        return [s.name for s in self.specs]

    def spec(self, name: StageName) -> StageSpec:
        return self._by_name[name]

    def enabled(self) -> list[StageSpec]:
        return [s for s in self.specs if s.enabled]

    def downstream(self, name: StageName) -> list[StageName]:
        """Stages that receive `name`'s produced seeds/candidates as backlog."""
        return list(self._by_name[name].produces_for)

    def as_dict(self) -> dict:
        return {"stages": [s.as_dict() for s in self.specs]}
