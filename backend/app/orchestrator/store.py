"""Orchestrator persistence (Phase 9A) — durable state + checkpoints for recovery.

Stores the latest `OrchestratorState` and a trail of `Checkpoint`s so a crashed run can resume from
where it stopped. ABC + InMemory (holds live objects) + SQLite (`asyncio.to_thread` + lock + WAL,
JSON-serialised via `as_dict`, rehydrated via `deserialize_state`). The InMemory store is enough for
tests and a single-process loop; SQLite gives real durability.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime

from app.orchestrator.models import Checkpoint, OrchestratorState, StageName
from app.orchestrator.state import deserialize_state


class OrchestratorStore(ABC):
    @abstractmethod
    async def save_state(self, state: OrchestratorState) -> None: ...

    @abstractmethod
    async def load_state(self) -> OrchestratorState | None: ...

    @abstractmethod
    async def save_checkpoint(self, checkpoint: Checkpoint) -> None: ...

    @abstractmethod
    async def latest_checkpoint(self) -> Checkpoint | None: ...

    async def close(self) -> None:
        return None


class InMemoryOrchestratorStore(OrchestratorStore):
    def __init__(self) -> None:
        self._state: OrchestratorState | None = None
        self._checkpoints: list[Checkpoint] = []

    async def save_state(self, state: OrchestratorState) -> None:
        self._state = state

    async def load_state(self) -> OrchestratorState | None:
        return self._state

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        self._checkpoints.append(checkpoint)

    async def latest_checkpoint(self) -> Checkpoint | None:
        return self._checkpoints[-1] if self._checkpoints else None

    async def checkpoint_count(self) -> int:
        return len(self._checkpoints)


class SQLiteOrchestratorStore(OrchestratorStore):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS orch_state (id INTEGER PRIMARY KEY, data TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS orch_checkpoints (cycle INTEGER PRIMARY KEY, data TEXT)"
        )
        self._conn.commit()

    async def save_state(self, state: OrchestratorState) -> None:
        payload = json.dumps(state.as_dict())

        def _save():
            with self._lock:
                self._conn.execute("DELETE FROM orch_state")
                self._conn.execute("INSERT INTO orch_state (id, data) VALUES (1, ?)", (payload,))
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def load_state(self) -> OrchestratorState | None:
        def _load():
            with self._lock:
                return self._conn.execute("SELECT data FROM orch_state WHERE id=1").fetchone()

        row = await asyncio.to_thread(_load)
        return deserialize_state(json.loads(row[0])) if row else None

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        payload = json.dumps(checkpoint.as_dict())

        def _save():
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO orch_checkpoints (cycle, data) VALUES (?, ?)",
                    (checkpoint.cycle, payload),
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def latest_checkpoint(self) -> Checkpoint | None:
        def _load():
            with self._lock:
                return self._conn.execute(
                    "SELECT data FROM orch_checkpoints ORDER BY cycle DESC LIMIT 1"
                ).fetchone()

        row = await asyncio.to_thread(_load)
        if not row:
            return None
        d = json.loads(row[0])
        return Checkpoint(
            cycle=d["cycle"],
            stage=StageName(d["stage"]) if d.get("stage") else None,
            created_at=datetime.fromisoformat(d["created_at"]),
            state=d["state"],
        )

    async def checkpoint_count(self) -> int:
        def _c():
            with self._lock:
                return self._conn.execute("SELECT COUNT(*) FROM orch_checkpoints").fetchone()[0]

        return await asyncio.to_thread(_c)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)
