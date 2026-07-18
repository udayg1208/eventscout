"""Rendered-discovery persistence (Phase 8E).

Persists the full reasoning record per url — the ProviderCandidate verdict, the hydration payloads,
and the discovered endpoints — so nothing is opaque. ABC + InMemory + SQLite.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RenderedRecord:
    url: str
    provider_candidate: dict
    hydration: list = field(default_factory=list)
    endpoints: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "provider_candidate": self.provider_candidate,
            "hydration": self.hydration,
            "endpoints": self.endpoints,
        }


class RenderedStore(ABC):
    @abstractmethod
    async def save(self, record: RenderedRecord) -> None: ...

    @abstractmethod
    async def get(self, url: str) -> RenderedRecord | None: ...

    @abstractmethod
    async def count(self) -> int: ...

    async def close(self) -> None:
        return None


class InMemoryRenderedStore(RenderedStore):
    def __init__(self) -> None:
        self._rows: dict[str, RenderedRecord] = {}

    async def save(self, record: RenderedRecord) -> None:
        self._rows[record.url] = record

    async def get(self, url: str) -> RenderedRecord | None:
        return self._rows.get(url)

    async def count(self) -> int:
        return len(self._rows)


class SQLiteRenderedStore(RenderedStore):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS rendered_records (url TEXT PRIMARY KEY, data TEXT)"
        )
        self._conn.commit()

    async def save(self, record: RenderedRecord) -> None:
        def _save():
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO rendered_records VALUES (?,?)",
                    (record.url, json.dumps(record.as_dict())),
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def get(self, url: str) -> RenderedRecord | None:
        def _get():
            with self._lock:
                row = self._conn.execute(
                    "SELECT data FROM rendered_records WHERE url=?", (url,)
                ).fetchone()
            return row

        row = await asyncio.to_thread(_get)
        if not row:
            return None
        d = json.loads(row[0])
        return RenderedRecord(d["url"], d["provider_candidate"], d["hydration"], d["endpoints"])

    async def count(self) -> int:
        def _c():
            with self._lock:
                return self._conn.execute("SELECT COUNT(*) FROM rendered_records").fetchone()[0]

        return await asyncio.to_thread(_c)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)
