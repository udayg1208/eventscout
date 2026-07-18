"""Recovery (Phase 9A) — the control plane survives crashes and poison stages.

Four mechanisms:
- **Checkpoint recovery** — every cycle snapshots state to the store; on start we restore the last.
- **Crash replay** — any stage left RUNNING when the process died is re-queued (lease stolen).
- **Partial retry** — a FAILED stage is retried on the scheduler's backoff up to `retry_max`.
- **Dead-letter queue** — a stage that exhausts its retries is parked in the DLQ (and marked
  DEAD_LETTER so the planner skips it) rather than blocking the loop; an operator can requeue it
  later.
Deterministic, clock-injected, no network.
"""

from __future__ import annotations

from datetime import datetime

from app.orchestrator.models import (
    Checkpoint,
    DeadLetterEntry,
    OrchestratorState,
    StageContext,
    StageName,
)
from app.orchestrator.pipeline import Pipeline


class DeadLetterQueue:
    def __init__(self, state: OrchestratorState) -> None:
        self._state = state

    def add(self, entry: DeadLetterEntry) -> None:
        self._state.dead_letter.append(entry)

    def list(self) -> list[DeadLetterEntry]:
        return list(self._state.dead_letter)

    def size(self) -> int:
        return len(self._state.dead_letter)

    def requeue(self, stage: StageName) -> list[DeadLetterEntry]:
        """Pull a stage's entries from the DLQ (operator action); returns what was removed."""
        removed = [e for e in self._state.dead_letter if e.stage is stage]
        self._state.dead_letter = [e for e in self._state.dead_letter if e.stage is not stage]
        return removed


class RecoveryManager:
    def __init__(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline

    def should_dead_letter(self, retry_count: int, retry_max: int) -> bool:
        return retry_count >= retry_max

    def dead_letter_entry(
        self, stage: StageName, cycle: int, attempts: int, error: str, now: datetime
    ) -> DeadLetterEntry:
        return DeadLetterEntry(
            stage=stage, cycle=cycle, attempts=attempts, error=error, created_at=now
        )

    def crash_replay_stages(self, state: OrchestratorState) -> list[StageName]:
        """Stages interrupted mid-run (status RUNNING) — replay these before normal planning."""
        return [n for n, st in state.stages.items() if st.status.value == "running"]

    def rebuild_context(
        self, state: OrchestratorState, stage: StageName, now: datetime
    ) -> StageContext:
        st = state.stage(stage)
        return StageContext(
            stage=stage,
            cycle=state.cycle,
            now=now,
            seeds=list(st.seeds),
            backlog=st.backlog,
        )

    def make_checkpoint(
        self, state: OrchestratorState, stage: StageName | None, now: datetime
    ) -> Checkpoint:
        return Checkpoint(cycle=state.cycle, stage=stage, created_at=now, state=state.as_dict())
