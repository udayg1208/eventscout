"""Metrics engine (Phase 9A) — one place that turns stage outcomes into rates.

Accumulates raw counters as stages run, then derives the dashboard numbers on demand: events/hour,
new providers/day, new sources/day, promotion & duplicate rates, crawl efficiency, AI usage, queue
sizes, per-stage latency, throughput, catalog size, and precision/recall/false-positives. Time comes
from an injected clock, so rates are exact and testable. Precision/recall need labelled feedback
(`record_feedback`) — until a downstream confirms/denies candidates they are honestly reported as 0.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.orchestrator.models import MetricsSnapshot, StageName, StageOutcome


class MetricsEngine:
    def __init__(self, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._start: datetime | None = None
        self.cycles = 0
        self.stages_run = 0
        self.discovered = 0
        self.promoted = 0  # new providers
        self.sources = 0  # new candidate sources into the inbox
        self.rejected = 0
        self.duplicates = 0
        self.pages = 0
        self.ai_calls = 0
        self.false_positives = 0
        self._true_positives = 0
        self._false_negatives = 0
        self.catalog_size = 0
        self._latency_sum: dict[str, float] = {}
        self._latency_n: dict[str, int] = {}
        self._queue_sizes: dict[str, int] = {}

    def start(self, now: datetime | None = None) -> None:
        self._start = now or self._clock()

    def observe_cycle(self) -> None:
        self.cycles += 1

    def observe_stage(self, stage: StageName, outcome: StageOutcome, duration_s: float) -> None:
        if self._start is None:
            self.start()
        self.stages_run += 1
        self.discovered += outcome.discovered
        self.promoted += outcome.promoted
        self.rejected += outcome.rejected
        self.duplicates += outcome.duplicates
        self.pages += outcome.pages
        self.ai_calls += outcome.ai_calls
        self.false_positives += outcome.false_positives
        if stage is StageName.ONBOARDING or stage is StageName.INBOX:
            self.sources += outcome.discovered
        key = stage.value
        self._latency_sum[key] = self._latency_sum.get(key, 0.0) + duration_s
        self._latency_n[key] = self._latency_n.get(key, 0) + 1

    def set_queue_sizes(self, sizes: dict[str, int]) -> None:
        self._queue_sizes = dict(sizes)

    def set_catalog_size(self, n: int) -> None:
        self.catalog_size = n

    def record_feedback(
        self, *, true_positives: int = 0, false_positives: int = 0, false_negatives: int = 0
    ) -> None:
        """Labelled downstream feedback — the only honest basis for precision/recall."""
        self._true_positives += true_positives
        self.false_positives += false_positives
        self._false_negatives += false_negatives

    # -- derived -------------------------------------------------------------

    def _elapsed(self, now: datetime | None) -> float:
        if self._start is None:
            return 0.0
        return max(0.0, ((now or self._clock()) - self._start).total_seconds())

    @staticmethod
    def _safe(numer: float, denom: float) -> float:
        return numer / denom if denom else 0.0

    def snapshot(self, now: datetime | None = None) -> MetricsSnapshot:
        elapsed = self._elapsed(now)
        hours = elapsed / 3_600.0
        days = elapsed / 86_400.0
        latency = {
            k: self._latency_sum[k] / self._latency_n[k]
            for k in self._latency_sum
            if self._latency_n.get(k)
        }
        tp, fp, fn = self._true_positives, self.false_positives, self._false_negatives
        return MetricsSnapshot(
            elapsed_s=elapsed,
            events_discovered=self.discovered,
            events_per_hour=self._safe(self.discovered, hours),
            new_providers=self.promoted,
            providers_per_day=self._safe(self.promoted, days),
            new_sources=self.sources,
            sources_per_day=self._safe(self.sources, days),
            promotion_rate=self._safe(self.promoted, self.discovered),
            duplicate_rate=self._safe(self.duplicates, self.discovered + self.duplicates),
            crawl_efficiency=self._safe(self.discovered, self.pages),
            ai_calls=self.ai_calls,
            queue_sizes=dict(self._queue_sizes),
            stage_latency_s=latency,
            throughput_per_cycle=self._safe(self.stages_run, self.cycles),
            catalog_size=self.catalog_size,
            precision=self._safe(tp, tp + fp),
            recall=self._safe(tp, tp + fn),
            false_positives=fp,
        )
