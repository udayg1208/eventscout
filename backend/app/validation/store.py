"""Validation persistence (Phase 10E) — the audit trail + retry state.

Persists every verification decision (evidence, reasons, confidence, verification path, timestamp)
and each seed's retry state. ABC + InMemory + SQLite (`asyncio.to_thread` + lock + WAL; JSON rows).
The audit trail is append-only; retry state upserts by seed key.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod

from app.validation.models import AuditRecord, RetryState


class ValidationStore(ABC):
    @abstractmethod
    async def save_audit(self, record: AuditRecord) -> None: ...

    @abstractmethod
    async def load_audit(self) -> list[AuditRecord]: ...

    @abstractmethod
    async def save_retry(self, state: RetryState) -> None: ...

    @abstractmethod
    async def load_retries(self) -> dict[str, RetryState]: ...

    async def close(self) -> None:
        return None


class InMemoryValidationStore(ValidationStore):
    def __init__(self) -> None:
        self._audit: list[AuditRecord] = []
        self._retries: dict[str, RetryState] = {}

    async def save_audit(self, record: AuditRecord) -> None:
        self._audit.append(record)

    async def load_audit(self) -> list[AuditRecord]:
        return list(self._audit)

    async def save_retry(self, state: RetryState) -> None:
        self._retries[state.seed_key] = state

    async def load_retries(self) -> dict[str, RetryState]:
        return dict(self._retries)


def _retry_from(d: dict) -> RetryState:
    return RetryState(
        seed_key=d["seed_key"],
        attempts=d["attempts"],
        next_run=d["next_run"],
        abandoned=d["abandoned"],
        last_decision=d.get("last_decision"),
    )


def _audit_from(d: dict) -> AuditRecord:
    return AuditRecord(
        seed_target=d["seed_target"],
        seed_kind=d["seed_kind"],
        decision=d["decision"],
        confidence=d["confidence"],
        evidence=d["evidence"],
        reasons=d["reasons"],
        verification_path=d["verification_path"],
        inbox_outcome=d.get("inbox_outcome"),
        timestamp=d["timestamp"],
    )


class SQLiteValidationStore(ValidationStore):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, data TEXT)")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS retries (seed_key TEXT PRIMARY KEY, data TEXT)"
        )
        self._conn.commit()

    async def save_audit(self, record: AuditRecord) -> None:
        payload = json.dumps(record.as_dict())

        def _save() -> None:
            with self._lock:
                self._conn.execute("INSERT INTO audit (data) VALUES (?)", (payload,))
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def load_audit(self) -> list[AuditRecord]:
        def _load():
            with self._lock:
                return self._conn.execute("SELECT data FROM audit ORDER BY id").fetchall()

        rows = await asyncio.to_thread(_load)
        return [_audit_from(json.loads(r[0])) for r in rows]

    async def save_retry(self, state: RetryState) -> None:
        payload = json.dumps(state.as_dict())

        def _save() -> None:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO retries (seed_key, data) VALUES (?, ?)",
                    (state.seed_key, payload),
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def load_retries(self) -> dict[str, RetryState]:
        def _load():
            with self._lock:
                return self._conn.execute("SELECT data FROM retries").fetchall()

        rows = await asyncio.to_thread(_load)
        return {s.seed_key: s for s in (_retry_from(json.loads(r[0])) for r in rows)}

    async def count_audit(self) -> int:
        def _c():
            with self._lock:
                return self._conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]

        return await asyncio.to_thread(_c)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)
