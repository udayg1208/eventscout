"""Checkpoint Store (Phase 8C) — incremental crawling only.

Persists per-URL crawl state (depth, visited-at, ETag, Last-Modified, last crawl, failure count,
robots version) so a second run skips URLs crawled recently and can issue conditional GETs. ABC +
InMemory + SQLite, mirroring the Repository / Discovery-Inbox pattern.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime

from app.discovery.expansion.models import CheckpointRecord


class CheckpointStore(ABC):
    @abstractmethod
    async def get(self, url: str) -> CheckpointRecord | None: ...

    @abstractmethod
    async def save(self, record: CheckpointRecord) -> None: ...

    @abstractmethod
    async def was_crawled_since(self, url: str, since: datetime) -> bool: ...

    @abstractmethod
    async def count(self) -> int: ...

    async def close(self) -> None:
        return None


class InMemoryCheckpointStore(CheckpointStore):
    def __init__(self) -> None:
        self._rows: dict[str, CheckpointRecord] = {}

    async def get(self, url: str) -> CheckpointRecord | None:
        return self._rows.get(url)

    async def save(self, record: CheckpointRecord) -> None:
        self._rows[record.url] = record

    async def was_crawled_since(self, url: str, since: datetime) -> bool:
        row = self._rows.get(url)
        return row is not None and row.last_crawl is not None and row.last_crawl >= since

    async def count(self) -> int:
        return len(self._rows)


def _dt(v):
    return v.isoformat() if v else None


def _pdt(v):
    return datetime.fromisoformat(v) if v else None


class SQLiteCheckpointStore(CheckpointStore):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS expansion_checkpoints "
            "(url TEXT PRIMARY KEY, data TEXT, last_crawl TEXT)"
        )
        self._conn.commit()

    async def get(self, url: str) -> CheckpointRecord | None:
        def _get():
            with self._lock:
                row = self._conn.execute(
                    "SELECT data FROM expansion_checkpoints WHERE url=?", (url,)
                ).fetchone()
            return row

        row = await asyncio.to_thread(_get)
        if not row:
            return None
        d = json.loads(row[0])
        return CheckpointRecord(
            url=d["url"],
            domain=d["domain"],
            depth=d["depth"],
            visited_at=_pdt(d["visited_at"]),
            etag=d["etag"],
            last_modified=d["last_modified"],
            last_crawl=_pdt(d["last_crawl"]),
            failure_count=d["failure_count"],
            robots_version=d["robots_version"],
        )

    async def save(self, record: CheckpointRecord) -> None:
        def _save():
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO expansion_checkpoints VALUES (?,?,?)",
                    (record.url, json.dumps(record.as_dict()), _dt(record.last_crawl)),
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def was_crawled_since(self, url: str, since: datetime) -> bool:
        def _q():
            with self._lock:
                row = self._conn.execute(
                    "SELECT last_crawl FROM expansion_checkpoints WHERE url=?", (url,)
                ).fetchone()
            return row

        row = await asyncio.to_thread(_q)
        return bool(row and row[0] and datetime.fromisoformat(row[0]) >= since)

    async def count(self) -> int:
        def _c():
            with self._lock:
                return self._conn.execute("SELECT COUNT(*) FROM expansion_checkpoints").fetchone()[
                    0
                ]

        return await asyncio.to_thread(_c)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)
