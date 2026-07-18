"""Onboarding persistence (Phase 7A).

Persists the lifecycle state, confidence/sandbox/packet/plan, review notes, promotion history,
confidence history, and a full audit log. Storage-agnostic (ABC + InMemory + SQLite), mirroring the
Repository / Discovery Inbox pattern. The candidate is serialized to JSON (nothing here needs to
query its internals); the audit log is a separate append-only table. No schema-breaking changes.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod

from app.onboarding.models import AuditEntry, OnboardingCandidate, OnboardingState


class OnboardingStore(ABC):
    @abstractmethod
    async def save(self, candidate: OnboardingCandidate) -> None: ...

    @abstractmethod
    async def get(self, key: str) -> OnboardingCandidate | None: ...

    @abstractmethod
    async def list(self, *, state: OnboardingState | None = None) -> list[OnboardingCandidate]: ...

    @abstractmethod
    async def append_audit(self, entry: AuditEntry) -> None: ...

    @abstractmethod
    async def audit_log(self, key: str | None = None) -> list[AuditEntry]: ...

    @abstractmethod
    async def count(self, *, state: OnboardingState | None = None) -> int: ...

    async def close(self) -> None:
        return None


class InMemoryOnboardingStore(OnboardingStore):
    def __init__(self) -> None:
        self._rows: dict[str, OnboardingCandidate] = {}
        self._audit: list[AuditEntry] = []

    async def save(self, candidate: OnboardingCandidate) -> None:
        self._rows[candidate.key] = candidate

    async def get(self, key: str) -> OnboardingCandidate | None:
        return self._rows.get(key)

    async def list(self, *, state=None) -> list[OnboardingCandidate]:
        items = [c for c in self._rows.values() if state is None or c.state == state]
        items.sort(key=lambda c: c.key)
        return items

    async def append_audit(self, entry: AuditEntry) -> None:
        self._audit.append(entry)

    async def audit_log(self, key: str | None = None) -> list[AuditEntry]:
        return [e for e in self._audit if key is None or e.key == key]

    async def count(self, *, state=None) -> int:
        return sum(1 for c in self._rows.values() if state is None or c.state == state)


def _dt(value):
    return value.isoformat() if value else None


class SQLiteOnboardingStore(OnboardingStore):
    """Persistent onboarding store. Candidate as JSON + a distinct append-only audit table."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS onboarding "
            "(key TEXT PRIMARY KEY, url TEXT, domain TEXT, feed_type TEXT, discovered_by TEXT, "
            " state TEXT, confidence REAL, data TEXT, created_at TEXT, updated_at TEXT, "
            " version INTEGER)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS onboarding_audit "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, timestamp TEXT, from_state TEXT, "
            " to_state TEXT, actor TEXT, reason TEXT)"
        )
        self._conn.commit()

    async def save(self, candidate: OnboardingCandidate) -> None:
        def _save() -> None:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO onboarding VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        candidate.key,
                        candidate.url,
                        candidate.domain,
                        candidate.feed_type,
                        candidate.discovered_by,
                        candidate.state.value,
                        candidate.confidence.total if candidate.confidence else None,
                        json.dumps(candidate.as_dict()),
                        _dt(candidate.created_at),
                        _dt(candidate.updated_at),
                        candidate.version,
                    ),
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def get(self, key: str) -> OnboardingCandidate | None:
        def _get():
            with self._lock:
                row = self._conn.execute(
                    "SELECT state, data FROM onboarding WHERE key=?", (key,)
                ).fetchone()
            return row

        row = await asyncio.to_thread(_get)
        return _light_candidate(json.loads(row[1])) if row else None

    async def list(self, *, state=None) -> list[OnboardingCandidate]:
        def _list():
            with self._lock:
                if state is None:
                    rows = self._conn.execute("SELECT data FROM onboarding ORDER BY key").fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT data FROM onboarding WHERE state=? ORDER BY key", (state.value,)
                    ).fetchall()
            return rows

        rows = await asyncio.to_thread(_list)
        return [_light_candidate(json.loads(r[0])) for r in rows]

    async def append_audit(self, entry: AuditEntry) -> None:
        def _append() -> None:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO onboarding_audit "
                    "(key, timestamp, from_state, to_state, actor, reason) VALUES (?,?,?,?,?,?)",
                    (
                        entry.key,
                        _dt(entry.timestamp),
                        entry.from_state,
                        entry.to_state,
                        entry.actor,
                        entry.reason,
                    ),
                )
                self._conn.commit()

        await asyncio.to_thread(_append)

    async def audit_log(self, key: str | None = None) -> list[AuditEntry]:
        def _log():
            with self._lock:
                if key is None:
                    rows = self._conn.execute(
                        "SELECT key, timestamp, from_state, to_state, actor, reason "
                        "FROM onboarding_audit ORDER BY id"
                    ).fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT key, timestamp, from_state, to_state, actor, reason "
                        "FROM onboarding_audit WHERE key=? ORDER BY id",
                        (key,),
                    ).fetchall()
            return rows

        rows = await asyncio.to_thread(_log)
        from datetime import datetime

        return [
            AuditEntry(
                key=r[0],
                timestamp=datetime.fromisoformat(r[1]) if r[1] else None,
                from_state=r[2],
                to_state=r[3],
                actor=r[4],
                reason=r[5],
            )
            for r in rows
        ]

    async def count(self, *, state=None) -> int:
        def _count() -> int:
            with self._lock:
                if state is None:
                    return self._conn.execute("SELECT COUNT(*) FROM onboarding").fetchone()[0]
                return self._conn.execute(
                    "SELECT COUNT(*) FROM onboarding WHERE state=?", (state.value,)
                ).fetchone()[0]

        return await asyncio.to_thread(_count)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)


def _light_candidate(data: dict) -> OnboardingCandidate:
    """Rehydrate the fields callers read back (state, key, snapshot, plan/packet as dicts under
    source_snapshot). The typed sub-objects aren't reconstructed — persistence is an audit/read
    surface, and no caller re-runs the pipeline from storage."""
    c = OnboardingCandidate(
        key=data["key"],
        url=data["url"],
        domain=data["domain"],
        feed_type=data["feed_type"],
        discovered_by=data["discovered_by"],
        source_snapshot=data.get("source_snapshot", {}),
        state=OnboardingState(data["state"]),
        review_notes=data.get("review_notes", []),
        promotion_history=data.get("promotion_history", []),
        confidence_history=data.get("confidence_history", []),
        version=data.get("version", 1),
    )
    # keep the serialized detail available without full typed rehydration
    c.source_snapshot = {**c.source_snapshot, "_persisted": data}
    return c
