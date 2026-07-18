"""AI-extraction persistence (Phase 6G / D4).

The Discovery Inbox candidate carries only the distilled AI verdict (discovery_confidence,
classification). The **full** provenance-bearing record — every extracted field with its source
snippet/reason/confidence, the ranked classification, the confidence breakdown, and the validation
verdict — lives here, keyed by url, so nothing is opaque and the candidate stays lean.

Storage-agnostic (ABC + InMemory + SQLite), mirroring the Repository / Discovery Inbox pattern.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.discovery.ai.models import (
    AIClassification,
    AIExtraction,
    DiscoveryConfidence,
    ValidationResult,
)


@dataclass
class AIExtractionRecord:
    """Everything D4 learned about one source page (the full audit trail)."""

    url: str
    extraction: AIExtraction
    classification: AIClassification
    confidence: DiscoveryConfidence
    validation: ValidationResult
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "extraction": self.extraction.as_dict(),
            "classification": self.classification.as_dict(),
            "confidence": self.confidence.as_dict(),
            "validation": self.validation.as_dict(),
            "extra": self.extra,
        }


class AIExtractionStore(ABC):
    @abstractmethod
    async def save(self, record: AIExtractionRecord) -> None: ...

    @abstractmethod
    async def get(self, url: str) -> AIExtractionRecord | None: ...

    @abstractmethod
    async def count(self) -> int: ...

    async def close(self) -> None:
        return None


class InMemoryAIExtractionStore(AIExtractionStore):
    def __init__(self) -> None:
        self._rows: dict[str, AIExtractionRecord] = {}

    async def save(self, record: AIExtractionRecord) -> None:
        self._rows[record.url] = record

    async def get(self, url: str) -> AIExtractionRecord | None:
        return self._rows.get(url)

    async def count(self) -> int:
        return len(self._rows)


class SQLiteAIExtractionStore(AIExtractionStore):
    """Persistent audit store. Full record serialized to JSON (no query needs its internals yet)."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS ai_extractions "
            "(url TEXT PRIMARY KEY, data TEXT, confidence REAL, classification TEXT)"
        )
        self._conn.commit()

    async def save(self, record: AIExtractionRecord) -> None:
        def _save() -> None:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO ai_extractions VALUES (?,?,?,?)",
                    (
                        record.url,
                        json.dumps(record.as_dict()),
                        record.confidence.total,
                        record.classification.primary.value
                        if record.classification.primary
                        else None,
                    ),
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def get(self, url: str) -> AIExtractionRecord | None:
        def _get() -> dict | None:
            with self._lock:
                row = self._conn.execute(
                    "SELECT data FROM ai_extractions WHERE url=?", (url,)
                ).fetchone()
            return json.loads(row[0]) if row else None

        data = await asyncio.to_thread(_get)
        return _record_from_dict(data) if data else None

    async def count(self) -> int:
        def _count() -> int:
            with self._lock:
                return self._conn.execute("SELECT COUNT(*) FROM ai_extractions").fetchone()[0]

        return await asyncio.to_thread(_count)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)


def _record_from_dict(data: dict) -> AIExtractionRecord:
    """Reconstruct a lightweight record from persisted JSON (audit/read use, not re-extraction).

    The nested AIExtraction/classification/etc. are kept as their serialized dicts under `extra`
    rather than fully rehydrated — persistence is an audit trail, and no caller re-runs the typed
    objects from storage. The scalar url is preserved for identity.
    """
    from app.discovery.ai.models import AIClassification, AIExtraction, DiscoveryConfidence

    url = data.get("url", "")
    conf = DiscoveryConfidence(total=data.get("confidence", {}).get("total", 0.0))
    validation = ValidationResult(passed=data.get("validation", {}).get("passed", False))
    return AIExtractionRecord(
        url=url,
        extraction=AIExtraction(url=url),
        classification=AIClassification(),
        confidence=conf,
        validation=validation,
        extra={"raw": data},
    )
