"""Growth stores (Phase 10F) — persist the queue, freshness, and cycle audit.

`GrowthStore` (ABC) with an in-memory implementation for tests and an SQLite one for durability
(JSON rows, INSERT OR REPLACE, `asyncio.to_thread` + a lock + WAL, `check_same_thread=False`),
mirroring every earlier phase's store pattern. Persists the growth queue's tasks, the freshness
records, and an append-only cycle audit so an autonomous run can resume. Additive; no network.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime

from app.growth.models import (
    CycleRecord,
    EntityKind,
    FreshnessRecord,
    GrowthTask,
    TaskKind,
    TaskState,
)


def _task_to_row(t: GrowthTask) -> dict:
    return t.as_dict() | {"max_attempts": t.max_attempts}


def _task_from_row(d: dict) -> GrowthTask:
    return GrowthTask(
        kind=TaskKind(d["kind"]),
        target=d["target"],
        priority=d["priority"],
        state=TaskState(d["state"]),
        attempts=d["attempts"],
        max_attempts=d.get("max_attempts", 3),
        cooldown_until=d["cooldown_until"],
        lease_owner=d.get("lease_owner", ""),
        lease_until=d.get("lease_until", 0),
        created_run=d.get("created_run", 0),
        reason=d.get("reason", ""),
        task_id=d.get("task_id", ""),
    )


def _fresh_to_row(r: FreshnessRecord) -> dict:
    return {
        "entity_id": r.entity_id,
        "kind": r.kind.value,
        "last_touched": r.last_touched.isoformat(),
        "ttl_seconds": r.ttl_seconds,
    }


def _fresh_from_row(d: dict) -> FreshnessRecord:
    return FreshnessRecord(
        entity_id=d["entity_id"],
        kind=EntityKind(d["kind"]),
        last_touched=datetime.fromisoformat(d["last_touched"]),
        ttl_seconds=d["ttl_seconds"],
    )


class GrowthStore(ABC):
    @abstractmethod
    async def save_queue(self, tasks: list[GrowthTask]) -> None: ...

    @abstractmethod
    async def load_queue(self) -> list[GrowthTask]: ...

    @abstractmethod
    async def save_freshness(self, records: list[FreshnessRecord]) -> None: ...

    @abstractmethod
    async def load_freshness(self) -> list[FreshnessRecord]: ...

    @abstractmethod
    async def append_cycle(self, record: CycleRecord) -> None: ...

    @abstractmethod
    async def load_cycles(self) -> list[CycleRecord]: ...


class InMemoryGrowthStore(GrowthStore):
    def __init__(self) -> None:
        self._queue: list[dict] = []
        self._freshness: list[dict] = []
        self._cycles: list[dict] = []

    async def save_queue(self, tasks: list[GrowthTask]) -> None:
        self._queue = [_task_to_row(t) for t in tasks]

    async def load_queue(self) -> list[GrowthTask]:
        return [_task_from_row(d) for d in self._queue]

    async def save_freshness(self, records: list[FreshnessRecord]) -> None:
        self._freshness = [_fresh_to_row(r) for r in records]

    async def load_freshness(self) -> list[FreshnessRecord]:
        return [_fresh_from_row(d) for d in self._freshness]

    async def append_cycle(self, record: CycleRecord) -> None:
        self._cycles.append(record.as_dict())

    async def load_cycles(self) -> list[CycleRecord]:
        return [CycleRecord(**d) for d in self._cycles]


class SQLiteGrowthStore(GrowthStore):
    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS growth_queue (
                dedup_key TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS growth_freshness (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS growth_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    async def save_queue(self, tasks: list[GrowthTask]) -> None:
        await asyncio.to_thread(self._save_queue, tasks)

    def _save_queue(self, tasks: list[GrowthTask]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM growth_queue")
            self._conn.executemany(
                "INSERT OR REPLACE INTO growth_queue (dedup_key, data) VALUES (?, ?)",
                [(t.dedup_key, json.dumps(_task_to_row(t))) for t in tasks],
            )
            self._conn.commit()

    async def load_queue(self) -> list[GrowthTask]:
        return await asyncio.to_thread(self._load_queue)

    def _load_queue(self) -> list[GrowthTask]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM growth_queue").fetchall()
        return [_task_from_row(json.loads(r[0])) for r in rows]

    async def save_freshness(self, records: list[FreshnessRecord]) -> None:
        await asyncio.to_thread(self._save_freshness, records)

    def _save_freshness(self, records: list[FreshnessRecord]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM growth_freshness")
            self._conn.executemany(
                "INSERT OR REPLACE INTO growth_freshness (key, data) VALUES (?, ?)",
                [(f"{r.kind.value}:{r.entity_id}", json.dumps(_fresh_to_row(r))) for r in records],
            )
            self._conn.commit()

    async def load_freshness(self) -> list[FreshnessRecord]:
        return await asyncio.to_thread(self._load_freshness)

    def _load_freshness(self) -> list[FreshnessRecord]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM growth_freshness").fetchall()
        return [_fresh_from_row(json.loads(r[0])) for r in rows]

    async def append_cycle(self, record: CycleRecord) -> None:
        await asyncio.to_thread(self._append_cycle, record)

    def _append_cycle(self, record: CycleRecord) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO growth_cycles (data) VALUES (?)", (json.dumps(record.as_dict()),)
            )
            self._conn.commit()

    async def load_cycles(self) -> list[CycleRecord]:
        return await asyncio.to_thread(self._load_cycles)

    def _load_cycles(self) -> list[CycleRecord]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM growth_cycles ORDER BY id").fetchall()
        return [CycleRecord(**json.loads(r[0])) for r in rows]
