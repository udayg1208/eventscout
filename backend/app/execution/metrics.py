"""Daily execution metrics (Phase 10A) — the operational dashboard for a real run.

Aggregates the numbers an operator watches each day: pages crawled/skipped, new domains, new
sources, new inbox candidates, accepted/rejected counts, duplicate rate, crawl cost, and discovery
precision. Fed by the `PageFetcher` stats, the crawler's report, and the `VerifyingInbox` callback.
Complements — does not replace — the orchestrator's `MetricsEngine` (which tracks the loop); this
tracks discovery *yield*. Precision here is accepted/(accepted+rejected) at the gate — a proxy for
true precision until humans confirm the inbox.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.discovery.models import CandidateSource
from app.execution.verification import VerificationResult


@dataclass
class DailyMetrics:
    date: str
    pages_crawled: int = 0
    pages_skipped: int = 0
    new_domains: int = 0
    new_sources: int = 0
    new_inbox_candidates: int = 0
    accepted: int = 0
    rejected: int = 0
    duplicates: int = 0
    duplicate_rate: float = 0.0
    crawl_cost_bytes: int = 0
    discovery_precision: float = 0.0

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "pages_crawled": self.pages_crawled,
            "pages_skipped": self.pages_skipped,
            "new_domains": self.new_domains,
            "new_sources": self.new_sources,
            "new_inbox_candidates": self.new_inbox_candidates,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "duplicates": self.duplicates,
            "duplicate_rate": round(self.duplicate_rate, 4),
            "crawl_cost_bytes": self.crawl_cost_bytes,
            "discovery_precision": round(self.discovery_precision, 4),
        }


class ExecutionMetrics:
    def __init__(self) -> None:
        self.pages_crawled = 0
        self.pages_skipped = 0
        self.accepted = 0
        self.rejected = 0
        self.duplicates = 0
        self.new_sources = 0
        self.crawl_cost_bytes = 0
        self._domains: set[str] = set()
        self._reject_reasons: dict[str, int] = {}

    # -- ingest --------------------------------------------------------------

    def record_pages(self, *, crawled: int = 0, skipped: int = 0, cost_bytes: int = 0) -> None:
        self.pages_crawled += crawled
        self.pages_skipped += skipped
        self.crawl_cost_bytes += cost_bytes

    def record_verification(
        self, candidate: CandidateSource, result: VerificationResult, outcome: str
    ) -> None:
        """The `VerifyingInbox.on_result` callback target."""
        if outcome in ("inserted", "updated"):
            self.accepted += 1
            if candidate.domain:
                self._domains.add(candidate.domain)
            if outcome == "inserted":
                self.new_sources += 1
        elif outcome == "duplicate":
            self.duplicates += 1
        else:  # rejected
            self.rejected += 1
            for reason in result.reasons:
                self._reject_reasons[reason] = self._reject_reasons.get(reason, 0) + 1

    # -- derive --------------------------------------------------------------

    @property
    def new_domains(self) -> int:
        return len(self._domains)

    @property
    def duplicate_rate(self) -> float:
        total = self.accepted + self.rejected + self.duplicates
        return self.duplicates / total if total else 0.0

    @property
    def discovery_precision(self) -> float:
        judged = self.accepted + self.rejected
        return self.accepted / judged if judged else 0.0

    def reject_reasons(self) -> dict[str, int]:
        return dict(self._reject_reasons)

    def snapshot(self, date: str) -> DailyMetrics:
        return DailyMetrics(
            date=date,
            pages_crawled=self.pages_crawled,
            pages_skipped=self.pages_skipped,
            new_domains=self.new_domains,
            new_sources=self.new_sources,
            new_inbox_candidates=self.new_sources,
            accepted=self.accepted,
            rejected=self.rejected,
            duplicates=self.duplicates,
            duplicate_rate=self.duplicate_rate,
            crawl_cost_bytes=self.crawl_cost_bytes,
            discovery_precision=self.discovery_precision,
        )
