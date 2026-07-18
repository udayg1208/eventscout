"""Freshness Engine (Phase 10F) — track entity age and recommend refreshes.

Records when each organizer / seed / validation / provider / expansion was last touched and, given
the current clock, reports which entities have aged past their per-kind TTL. Stale organizers become
`ORGANIZER_REFRESH` tasks; other stale entities become `EXPANSION` re-work. Nothing is deleted — an
aged entity is *recommended* for refresh, never removed. Deterministic; no network.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.growth.models import EntityKind, FreshnessRecord, GrowthTask, TaskKind

# Default TTLs — how long before an entity is considered stale (seconds).
DEFAULT_TTL: dict[EntityKind, int] = {
    EntityKind.ORGANIZER: 7 * 86_400,  # re-check an organizer weekly
    EntityKind.SEED: 3 * 86_400,
    EntityKind.VALIDATION: 14 * 86_400,
    EntityKind.PROVIDER: 30 * 86_400,
    EntityKind.EXPANSION: 7 * 86_400,
}

# A stale entity of this kind should be refreshed via this task kind.
_REFRESH_TASK: dict[EntityKind, TaskKind] = {
    EntityKind.ORGANIZER: TaskKind.ORGANIZER_REFRESH,
    EntityKind.SEED: TaskKind.VALIDATION,
    EntityKind.VALIDATION: TaskKind.VALIDATION,
    EntityKind.PROVIDER: TaskKind.PRODUCTION_MONITOR,
    EntityKind.EXPANSION: TaskKind.EXPANSION,
}


class FreshnessEngine:
    def __init__(
        self,
        *,
        ttl: dict[EntityKind, int] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._ttl = {**DEFAULT_TTL, **(ttl or {})}
        self._clock = clock
        self._records: dict[str, FreshnessRecord] = {}

    def _key(self, entity_id: str, kind: EntityKind) -> str:
        return f"{kind.value}:{entity_id}"

    def touch(self, entity_id: str, kind: EntityKind, *, now: datetime | None = None) -> None:
        now = now or self._clock()
        self._records[self._key(entity_id, kind)] = FreshnessRecord(
            entity_id=entity_id, kind=kind, last_touched=now, ttl_seconds=self._ttl[kind]
        )

    def record(self, entity_id: str, kind: EntityKind) -> FreshnessRecord | None:
        return self._records.get(self._key(entity_id, kind))

    def records(self) -> list[FreshnessRecord]:
        return list(self._records.values())

    def age_seconds(
        self, entity_id: str, kind: EntityKind, now: datetime | None = None
    ) -> float | None:
        rec = self.record(entity_id, kind)
        return None if rec is None else rec.age_seconds(now or self._clock())

    def stale(
        self, *, now: datetime | None = None, kind: EntityKind | None = None
    ) -> list[FreshnessRecord]:
        now = now or self._clock()
        out = [
            r
            for r in self._records.values()
            if r.is_stale(now) and (kind is None or r.kind is kind)
        ]
        out.sort(key=lambda r: r.age_seconds(now), reverse=True)
        return out

    def recommend_refreshes(
        self, *, now: datetime | None = None, limit: int = 50
    ) -> list[GrowthTask]:
        now = now or self._clock()
        tasks: list[GrowthTask] = []
        for rec in self.stale(now=now)[:limit]:
            tasks.append(
                GrowthTask(
                    kind=_REFRESH_TASK[rec.kind],
                    target=rec.entity_id,
                    reason=f"stale:{rec.kind.value}",
                )
            )
        return tasks

    def snapshot(self, *, now: datetime | None = None) -> list[dict]:
        now = now or self._clock()
        return [r.as_dict(now) for r in self._records.values()]
