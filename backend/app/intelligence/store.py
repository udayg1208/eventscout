"""Intelligence Store — storage-independent persistence for the intelligence layer.

Holds the previous run's fingerprint snapshot (for change detection) and the latest report.
In-memory today; a persisted backend (SQLite/Postgres) implements the same interface later
with no change to the engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.intelligence.models import EventFingerprint, IntelligenceReport


class IntelligenceStore(ABC):
    @abstractmethod
    def get_snapshot(self) -> dict[str, EventFingerprint]:
        """The previous run's fingerprints (empty on first run)."""

    @abstractmethod
    def save_snapshot(self, snapshot: dict[str, EventFingerprint]) -> None: ...

    @abstractmethod
    def get_report(self) -> IntelligenceReport | None: ...

    @abstractmethod
    def save_report(self, report: IntelligenceReport) -> None: ...


class InMemoryIntelligenceStore(IntelligenceStore):
    def __init__(self) -> None:
        self._snapshot: dict[str, EventFingerprint] = {}
        self._report: IntelligenceReport | None = None

    def get_snapshot(self) -> dict[str, EventFingerprint]:
        return dict(self._snapshot)

    def save_snapshot(self, snapshot: dict[str, EventFingerprint]) -> None:
        self._snapshot = dict(snapshot)

    def get_report(self) -> IntelligenceReport | None:
        return self._report

    def save_report(self, report: IntelligenceReport) -> None:
        self._report = report
