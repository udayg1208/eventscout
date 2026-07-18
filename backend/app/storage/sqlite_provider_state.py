"""SQLite implementation of `ProviderStateStore` — the first backend.

One durable row per provider. `capabilities` and `extra` are stored as JSON so future
Scheduler/Worker/Retry/Analytics fields need no schema change. Each `update_after_*` is a
single locked read-modify-write (offloaded via ``asyncio.to_thread``), so concurrent
updates to the same provider serialize correctly and never lose a write.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from datetime import UTC, datetime

from app.storage.provider_state import (
    DEFAULT_RETRY_POLICY,
    CircuitState,
    HealthStatus,
    HealthSummary,
    ProviderState,
    ProviderStateStore,
    RetryPolicy,
    apply_failure,
    apply_success,
    new_provider_state,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_state (
    provider_id          TEXT PRIMARY KEY,
    provider_version     INTEGER NOT NULL DEFAULT 1,
    capabilities         TEXT NOT NULL DEFAULT '{}',   -- JSON
    enabled              INTEGER NOT NULL DEFAULT 1,
    health_status        TEXT NOT NULL DEFAULT 'unknown',
    circuit_state        TEXT NOT NULL DEFAULT 'closed',
    last_success_at      TEXT,
    last_attempt_at      TEXT,
    next_run_at          TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    total_runs           INTEGER NOT NULL DEFAULT 0,
    total_successes      INTEGER NOT NULL DEFAULT 0,
    total_failures       INTEGER NOT NULL DEFAULT 0,
    avg_execution_ms     REAL NOT NULL DEFAULT 0,
    avg_events           REAL NOT NULL DEFAULT 0,
    checkpoint           TEXT,
    cursor               TEXT,
    retry_count          INTEGER NOT NULL DEFAULT 0,
    last_error           TEXT,
    last_error_at        TEXT,
    created_at           TEXT,
    updated_at           TEXT,
    extra                TEXT NOT NULL DEFAULT '{}'     -- JSON (forward-compat)
);
CREATE INDEX IF NOT EXISTS idx_provider_state_due ON provider_state(enabled, next_run_at);
CREATE INDEX IF NOT EXISTS idx_provider_state_health ON provider_state(health_status);
"""

_COLUMNS = (
    "provider_id, provider_version, capabilities, enabled, health_status, circuit_state, "
    "last_success_at, last_attempt_at, next_run_at, consecutive_failures, total_runs, "
    "total_successes, total_failures, avg_execution_ms, avg_events, checkpoint, cursor, "
    "retry_count, last_error, last_error_at, created_at, updated_at, extra"
)
_UPSERT_SQL = (
    f"INSERT OR REPLACE INTO provider_state ({_COLUMNS}) VALUES ("
    + ", ".join(f":{name.strip()}" for name in _COLUMNS.split(","))
    + ")"
)


class SQLiteProviderStateStore(ProviderStateStore):
    """SQLite-backed provider state. File path for durability, ``:memory:`` for tests."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- async interface -----------------------------------------------------------

    async def get_provider_state(self, provider_id: str) -> ProviderState | None:
        return await asyncio.to_thread(self._get_sync, provider_id)

    async def save_provider_state(self, state: ProviderState) -> None:
        await asyncio.to_thread(self._save_sync, state)

    async def update_after_run(
        self,
        provider_id: str,
        *,
        at: datetime,
        execution_ms: float,
        events_discovered: int,
        checkpoint: str | None = None,
        cursor: str | None = None,
        policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    ) -> ProviderState:
        return await asyncio.to_thread(
            self._update_sync,
            provider_id,
            lambda state: apply_success(
                state,
                at=at,
                execution_ms=execution_ms,
                events_discovered=events_discovered,
                checkpoint=checkpoint,
                cursor=cursor,
                policy=policy,
            ),
            at,
        )

    async def update_after_failure(
        self,
        provider_id: str,
        *,
        at: datetime,
        error: str,
        execution_ms: float = 0.0,
        policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    ) -> ProviderState:
        return await asyncio.to_thread(
            self._update_sync,
            provider_id,
            lambda state: apply_failure(
                state, at=at, error=error, execution_ms=execution_ms, policy=policy
            ),
            at,
        )

    async def due_providers(self, now: datetime, *, limit: int | None = None) -> list[str]:
        return await asyncio.to_thread(self._due_sync, now, limit)

    async def reset_circuit(self, provider_id: str, *, at: datetime | None = None) -> None:
        await asyncio.to_thread(self._reset_circuit_sync, provider_id, at)

    async def enable_provider(self, provider_id: str, *, at: datetime | None = None) -> None:
        await asyncio.to_thread(self._set_enabled_sync, provider_id, True, at)

    async def disable_provider(self, provider_id: str, *, at: datetime | None = None) -> None:
        await asyncio.to_thread(self._set_enabled_sync, provider_id, False, at)

    async def provider_health_summary(self) -> HealthSummary:
        return await asyncio.to_thread(self._summary_sync)

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    # --- sync work (serialized by the lock) ----------------------------------------

    def _get_sync(self, provider_id: str) -> ProviderState | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM provider_state WHERE provider_id = ?", (provider_id,)
            ).fetchone()
        return _row_to_state(row) if row else None

    def _save_sync(self, state: ProviderState) -> None:
        with self._lock:
            self._conn.execute(_UPSERT_SQL, _state_to_params(state))
            self._conn.commit()

    def _update_sync(self, provider_id, transition, at) -> ProviderState:
        # Whole read-modify-write under one lock ⇒ concurrent updates never lose a write.
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM provider_state WHERE provider_id = ?", (provider_id,)
            ).fetchone()
            state = _row_to_state(row) if row else new_provider_state(provider_id, at=at)
            new_state = transition(state)
            self._conn.execute(_UPSERT_SQL, _state_to_params(new_state))
            self._conn.commit()
        return new_state

    def _due_sync(self, now: datetime, limit: int | None) -> list[str]:
        sql = (
            "SELECT provider_id FROM provider_state "
            "WHERE enabled = 1 AND (next_run_at IS NULL OR next_run_at <= :now) "
            "ORDER BY next_run_at ASC"  # NULLs (never run) sort first ⇒ highest priority
        )
        params: dict[str, object] = {"now": now.isoformat()}
        if limit is not None:
            sql += " LIMIT :limit"
            params["limit"] = limit
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [row["provider_id"] for row in rows]

    def _reset_circuit_sync(self, provider_id: str, at: datetime | None) -> None:
        stamp = (at or datetime.now(UTC)).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE provider_state SET circuit_state = 'closed', consecutive_failures = 0, "
                "retry_count = 0, "
                "health_status = CASE WHEN total_runs > 0 THEN 'healthy' ELSE 'unknown' END, "
                "updated_at = ? WHERE provider_id = ?",
                (stamp, provider_id),
            )
            self._conn.commit()

    def _set_enabled_sync(self, provider_id: str, enabled: bool, at: datetime | None) -> None:
        stamp = (at or datetime.now(UTC)).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE provider_state SET enabled = ?, updated_at = ? WHERE provider_id = ?",
                (1 if enabled else 0, stamp, provider_id),
            )
            self._conn.commit()

    def _summary_sync(self) -> HealthSummary:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) AS n FROM provider_state").fetchone()["n"]
            enabled = self._conn.execute(
                "SELECT COUNT(*) AS n FROM provider_state WHERE enabled = 1"
            ).fetchone()["n"]
            by_health = {
                row["health_status"]: row["n"]
                for row in self._conn.execute(
                    "SELECT health_status, COUNT(*) AS n FROM provider_state GROUP BY health_status"
                ).fetchall()
            }
            by_circuit = {
                row["circuit_state"]: row["n"]
                for row in self._conn.execute(
                    "SELECT circuit_state, COUNT(*) AS n FROM provider_state GROUP BY circuit_state"
                ).fetchall()
            }
            agg = self._conn.execute(
                "SELECT COALESCE(SUM(total_runs),0) AS runs, "
                "COALESCE(SUM(total_successes),0) AS successes, "
                "COALESCE(SUM(total_failures),0) AS failures, "
                "COALESCE(AVG(avg_execution_ms),0) AS avg_ms FROM provider_state"
            ).fetchone()
        runs = agg["runs"]
        return HealthSummary(
            total=total,
            enabled=enabled,
            disabled=total - enabled,
            by_health=by_health,
            by_circuit=by_circuit,
            total_runs=runs,
            total_successes=agg["successes"],
            total_failures=agg["failures"],
            success_rate=round(agg["successes"] / runs, 4) if runs else 0.0,
            avg_execution_ms=round(agg["avg_ms"], 2),
        )

    def _close_sync(self) -> None:
        with self._lock:
            self._conn.close()


# --- row <-> model mapping ---------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _state_to_params(state: ProviderState) -> dict[str, object]:
    return {
        "provider_id": state.provider_id,
        "provider_version": state.provider_version,
        "capabilities": json.dumps(state.capabilities, sort_keys=True),
        "enabled": 1 if state.enabled else 0,
        "health_status": state.health_status.value,
        "circuit_state": state.circuit_state.value,
        "last_success_at": _iso(state.last_success_at),
        "last_attempt_at": _iso(state.last_attempt_at),
        "next_run_at": _iso(state.next_run_at),
        "consecutive_failures": state.consecutive_failures,
        "total_runs": state.total_runs,
        "total_successes": state.total_successes,
        "total_failures": state.total_failures,
        "avg_execution_ms": state.avg_execution_ms,
        "avg_events": state.avg_events,
        "checkpoint": state.checkpoint,
        "cursor": state.cursor,
        "retry_count": state.retry_count,
        "last_error": state.last_error,
        "last_error_at": _iso(state.last_error_at),
        "created_at": _iso(state.created_at),
        "updated_at": _iso(state.updated_at),
        "extra": json.dumps(state.extra, sort_keys=True),
    }


def _row_to_state(row: sqlite3.Row) -> ProviderState:
    return ProviderState(
        provider_id=row["provider_id"],
        provider_version=row["provider_version"],
        capabilities=json.loads(row["capabilities"]),
        enabled=bool(row["enabled"]),
        health_status=HealthStatus(row["health_status"]),
        circuit_state=CircuitState(row["circuit_state"]),
        last_success_at=_dt(row["last_success_at"]),
        last_attempt_at=_dt(row["last_attempt_at"]),
        next_run_at=_dt(row["next_run_at"]),
        consecutive_failures=row["consecutive_failures"],
        total_runs=row["total_runs"],
        total_successes=row["total_successes"],
        total_failures=row["total_failures"],
        avg_execution_ms=row["avg_execution_ms"],
        avg_events=row["avg_events"],
        checkpoint=row["checkpoint"],
        cursor=row["cursor"],
        retry_count=row["retry_count"],
        last_error=row["last_error"],
        last_error_at=_dt(row["last_error_at"]),
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
        extra=json.loads(row["extra"]),
    )
