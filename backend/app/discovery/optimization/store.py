"""Discovery-optimization data model + persistence (Phase 8A).

`DiscoveryRecord` is the shared *historical* unit every optimizer stage consumes — one discovered
source with its downstream onboarding/production outcome. This module owns it (and imports nothing
from sibling stages, so there are no cycles). `OptimizationStore` persists optimization reports as
plain dicts (append-only history) — it never imports the report types, keeping the dependency graph
clean.

Everything here is READ-ONLY analytics input: the optimizer observes what discovery already did. It
never touches the catalog, discovery engine, onboarding, or production.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DiscoveryRecord:
    """One discovered source + its observed downstream outcome (the historical signal)."""

    url: str
    domain: str
    feed_type: str  # rss / jsonld_event / next_data / search_result / ai_extracted / …
    discovered_by: str  # crawl / search / ai
    search_query: str | None = None
    search_rank: int | None = None
    city: str | None = None
    state: str | None = None
    technologies: list[str] = field(default_factory=list)
    organization: str | None = None
    community: str | None = None
    university: str | None = None
    discovery_confidence: float | None = None
    # onboarding (7A) outcome
    onboarding_state: str | None = (
        None  # promoted / manual_review / rejected / duplicate / failed_sandbox
    )
    sandbox_quality: float = 0.0
    # production (7B) outcome
    production_state: str | None = None  # active / rolled_back / None
    # observed quality signals
    duplicate_rate: float = 0.0
    event_count: int = 0  # events observed / plausible (richness)
    freshness_hours: float | None = None
    crawl_attempts: int = 1
    crawl_failures: int = 0

    @property
    def approved(self) -> bool:
        return self.onboarding_state in ("promoted", "approved")

    @property
    def active(self) -> bool:
        return self.production_state == "active"

    @property
    def rejected(self) -> bool:
        return self.onboarding_state in ("rejected", "duplicate", "failed_sandbox", "blacklisted")


class OptimizationStore(ABC):
    @abstractmethod
    async def save_report(self, report: dict) -> None: ...

    @abstractmethod
    async def latest(self) -> dict | None: ...

    @abstractmethod
    async def history(self) -> list[dict]: ...

    async def close(self) -> None:
        return None


class InMemoryOptimizationStore(OptimizationStore):
    def __init__(self) -> None:
        self._reports: list[dict] = []

    async def save_report(self, report: dict) -> None:
        self._reports.append(report)

    async def latest(self) -> dict | None:
        return self._reports[-1] if self._reports else None

    async def history(self) -> list[dict]:
        return list(self._reports)


class SQLiteOptimizationStore(OptimizationStore):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS optimization_reports "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT)"
        )
        self._conn.commit()

    async def save_report(self, report: dict) -> None:
        def _save() -> None:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO optimization_reports (data) VALUES (?)", (json.dumps(report),)
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def latest(self) -> dict | None:
        def _get():
            with self._lock:
                row = self._conn.execute(
                    "SELECT data FROM optimization_reports ORDER BY id DESC LIMIT 1"
                ).fetchone()
            return json.loads(row[0]) if row else None

        return await asyncio.to_thread(_get)

    async def history(self) -> list[dict]:
        def _hist():
            with self._lock:
                rows = self._conn.execute(
                    "SELECT data FROM optimization_reports ORDER BY id"
                ).fetchall()
            return [json.loads(r[0]) for r in rows]

        return await asyncio.to_thread(_hist)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)
