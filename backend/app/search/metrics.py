"""Search Metrics — operational observability for the retrieval pipeline.

Distinct from business analytics (popular queries, CTR) and from provider/ingestion
analytics. Tracks the mechanics of serving a search: retrieval vs. ranking latency,
per-retriever and fused candidate counts, and zero-result rate. In-memory today; a
Prometheus/OTel exporter is a later drop-in.
"""

from __future__ import annotations

from collections import Counter


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = max(0, min(len(sorted_values) - 1, round(pct / 100 * (len(sorted_values) - 1))))
    return round(sorted_values[k], 3)


class SearchMetrics:
    def __init__(self, *, window: int = 1000) -> None:
        self._window = window
        self.total_searches = 0
        self.zero_result_searches = 0
        self._retrieval_ms: list[float] = []
        self._ranking_ms: list[float] = []
        self._total_ms: list[float] = []
        self._candidates_per_retriever: Counter[str] = Counter()
        self._retriever_invocations: Counter[str] = Counter()
        self._fused_total = 0
        self._ranked_total = 0

    def record(
        self,
        *,
        retrieval_ms: float,
        ranking_ms: float,
        candidates_by_source: dict[str, int],
        fused_count: int,
        result_count: int,
    ) -> None:
        self.total_searches += 1
        if result_count == 0:
            self.zero_result_searches += 1
        self._push(self._retrieval_ms, retrieval_ms)
        self._push(self._ranking_ms, ranking_ms)
        self._push(self._total_ms, retrieval_ms + ranking_ms)
        for source, n in candidates_by_source.items():
            self._candidates_per_retriever[source] += n
            self._retriever_invocations[source] += 1
        self._fused_total += fused_count
        self._ranked_total += result_count

    def _push(self, series: list[float], value: float) -> None:
        series.append(value)
        if len(series) > self._window:
            del series[0]

    def _latency(self, series: list[float]) -> dict[str, float]:
        ordered = sorted(series)
        return {
            "p50": _percentile(ordered, 50),
            "p95": _percentile(ordered, 95),
            "p99": _percentile(ordered, 99),
        }

    def snapshot(self) -> dict:
        n = self.total_searches
        avg_candidates = {
            source: round(total / self._retriever_invocations[source], 2)
            for source, total in self._candidates_per_retriever.items()
        }
        return {
            "total_searches": n,
            "zero_result_searches": self.zero_result_searches,
            "zero_result_rate": round(self.zero_result_searches / n, 4) if n else 0.0,
            "retrieval_latency_ms": self._latency(self._retrieval_ms),
            "ranking_latency_ms": self._latency(self._ranking_ms),
            "total_latency_ms": self._latency(self._total_ms),
            "avg_candidates_per_retriever": avg_candidates,
            "avg_fused_candidates": round(self._fused_total / n, 2) if n else 0.0,
            "avg_ranked_results": round(self._ranked_total / n, 2) if n else 0.0,
        }
