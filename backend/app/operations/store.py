"""Operations persistence (Phase 7B).

Persists production history (registrations), canary history, rollback history, learning reports, and
calibration history. Storage-agnostic (ABC + InMemory + SQLite). Registrations upsert by
provider_id; the four history streams are append-only (nothing is ever deleted — rollbacks keep
their record). No schema-breaking changes.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod

from app.operations.registry import ProductionRegistration, ProductionState


class OperationsStore(ABC):
    @abstractmethod
    async def save_registration(self, reg: ProductionRegistration) -> None: ...

    @abstractmethod
    async def get_registration(self, provider_id: str) -> dict | None: ...

    @abstractmethod
    async def list_registrations(self, *, state: ProductionState | None = None) -> list[dict]: ...

    @abstractmethod
    async def append_canary(self, entry: dict) -> None: ...

    @abstractmethod
    async def append_rollback(self, entry: dict) -> None: ...

    @abstractmethod
    async def append_learning(self, report: dict) -> None: ...

    @abstractmethod
    async def append_calibration(self, model: dict) -> None: ...

    @abstractmethod
    async def history(self, stream: str) -> list[dict]: ...

    async def close(self) -> None:
        return None


class InMemoryOperationsStore(OperationsStore):
    def __init__(self) -> None:
        self._regs: dict[str, dict] = {}
        self._streams: dict[str, list[dict]] = {
            "canary": [],
            "rollback": [],
            "learning": [],
            "calibration": [],
        }

    async def save_registration(self, reg: ProductionRegistration) -> None:
        self._regs[reg.provider_id] = reg.as_dict()

    async def get_registration(self, provider_id: str) -> dict | None:
        return self._regs.get(provider_id)

    async def list_registrations(self, *, state=None) -> list[dict]:
        rows = list(self._regs.values())
        if state is not None:
            rows = [r for r in rows if r["state"] == state.value]
        return sorted(rows, key=lambda r: r["provider_id"])

    async def append_canary(self, entry: dict) -> None:
        self._streams["canary"].append(entry)

    async def append_rollback(self, entry: dict) -> None:
        self._streams["rollback"].append(entry)

    async def append_learning(self, report: dict) -> None:
        self._streams["learning"].append(report)

    async def append_calibration(self, model: dict) -> None:
        self._streams["calibration"].append(model)

    async def history(self, stream: str) -> list[dict]:
        return list(self._streams.get(stream, []))


class SQLiteOperationsStore(OperationsStore):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS production "
            "(provider_id TEXT PRIMARY KEY, domain TEXT, provider_type TEXT, state TEXT, "
            " updated_at TEXT, data TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS ops_history "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, stream TEXT, data TEXT)"
        )
        self._conn.commit()

    async def save_registration(self, reg: ProductionRegistration) -> None:
        def _save() -> None:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO production VALUES (?,?,?,?,?,?)",
                    (
                        reg.provider_id,
                        reg.domain,
                        reg.provider_type,
                        reg.state.value,
                        reg.updated_at.isoformat() if reg.updated_at else None,
                        json.dumps(reg.as_dict()),
                    ),
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def get_registration(self, provider_id: str) -> dict | None:
        def _get():
            with self._lock:
                row = self._conn.execute(
                    "SELECT data FROM production WHERE provider_id=?", (provider_id,)
                ).fetchone()
            return json.loads(row[0]) if row else None

        return await asyncio.to_thread(_get)

    async def list_registrations(self, *, state=None) -> list[dict]:
        def _list():
            with self._lock:
                if state is None:
                    rows = self._conn.execute(
                        "SELECT data FROM production ORDER BY provider_id"
                    ).fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT data FROM production WHERE state=? ORDER BY provider_id",
                        (state.value,),
                    ).fetchall()
            return [json.loads(r[0]) for r in rows]

        return await asyncio.to_thread(_list)

    async def _append(self, stream: str, data: dict) -> None:
        def _ins() -> None:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO ops_history (stream, data) VALUES (?,?)",
                    (stream, json.dumps(data)),
                )
                self._conn.commit()

        await asyncio.to_thread(_ins)

    async def append_canary(self, entry: dict) -> None:
        await self._append("canary", entry)

    async def append_rollback(self, entry: dict) -> None:
        await self._append("rollback", entry)

    async def append_learning(self, report: dict) -> None:
        await self._append("learning", report)

    async def append_calibration(self, model: dict) -> None:
        await self._append("calibration", model)

    async def history(self, stream: str) -> list[dict]:
        def _hist():
            with self._lock:
                rows = self._conn.execute(
                    "SELECT data FROM ops_history WHERE stream=? ORDER BY id", (stream,)
                ).fetchall()
            return [json.loads(r[0]) for r in rows]

        return await asyncio.to_thread(_hist)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)
