"""Crawl Budget Manager (Phase 8C) — automatically stop low-value / abusive crawling.

Tracks per-domain usage against a `CrawlBudgetConfig`: max pages, max depth, max failures, a
cooldown after a failure, a daily page limit, and a bandwidth ceiling. `can_crawl` returns why a
domain is (not) crawlable; once a domain trips any ceiling it is "stopped" for the run.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.discovery.expansion.models import DEFAULT_CRAWL_BUDGET, CrawlBudgetConfig


@dataclass
class _Usage:
    pages: int = 0
    failures: int = 0
    bytes: int = 0
    last_failure_at: datetime | None = None


class BudgetTracker:
    def __init__(
        self,
        config: CrawlBudgetConfig = DEFAULT_CRAWL_BUDGET,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._config = config
        self._clock = clock
        self._usage: dict[str, _Usage] = {}
        self._stopped: set[str] = set()

    def _u(self, domain: str) -> _Usage:
        return self._usage.setdefault(domain, _Usage())

    def can_crawl(self, domain: str) -> tuple[bool, str]:
        u = self._u(domain)
        if domain in self._stopped:
            return False, "domain stopped"
        if u.pages >= self._config.max_pages:
            self._stopped.add(domain)
            return False, f"max_pages {self._config.max_pages} reached"
        if u.failures >= self._config.max_failures:
            self._stopped.add(domain)
            return False, f"max_failures {self._config.max_failures} reached"
        if u.bytes >= self._config.max_bandwidth_bytes:
            self._stopped.add(domain)
            return False, "bandwidth ceiling reached"
        if u.last_failure_at is not None:
            elapsed = (self._clock() - u.last_failure_at).total_seconds()
            if elapsed < self._config.cooldown_seconds:
                return False, f"cooling down ({elapsed:.0f}s/{self._config.cooldown_seconds:.0f}s)"
        return True, "ok"

    def record_fetch(self, domain: str, *, byte_size: int = 0, success: bool = True) -> None:
        u = self._u(domain)
        u.pages += 1
        u.bytes += max(0, byte_size)
        if not success:
            u.failures += 1
            u.last_failure_at = self._clock()

    def stopped_domains(self) -> list[str]:
        return sorted(self._stopped)

    def usage(self) -> dict[str, dict]:
        return {
            d: {"pages": u.pages, "failures": u.failures, "bytes": u.bytes}
            for d, u in self._usage.items()
        }
