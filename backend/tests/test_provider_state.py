"""Phase 3B: Provider State Store.

Covers the persistent per-provider memory and its transitions: successful runs and
running averages, repeated failures, circuit opening + recovery, checkpoint/cursor
persistence, due scheduling, enable/disable, restart durability, concurrent updates
(no lost writes), and the fleet health summary.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.storage.provider_state import (
    CircuitState,
    HealthStatus,
    ProviderState,
    RetryPolicy,
    new_provider_state,
)
from app.storage.sqlite_provider_state import SQLiteProviderStateStore


def run(coro):
    return asyncio.run(coro)


T0 = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _at(minutes: float = 0) -> datetime:
    return T0 + timedelta(minutes=minutes)


# Small, explicit policy so thresholds/backoff are easy to assert.
POLICY = RetryPolicy(
    failure_threshold=3,
    base_backoff_seconds=60,
    max_backoff_seconds=600,
    circuit_cooldown_seconds=900,
    refresh_interval_seconds=3600,
)


def _store() -> SQLiteProviderStateStore:
    return SQLiteProviderStateStore()


# --------------------------- successful runs ---------------------------


def test_update_after_run_records_success():
    store = _store()
    state = run(
        store.update_after_run(
            "p",
            at=T0,
            execution_ms=120.0,
            events_discovered=10,
            checkpoint="h1",
            cursor="c1",
            policy=POLICY,
        )
    )
    assert (state.total_runs, state.total_successes, state.total_failures) == (1, 1, 0)
    assert state.consecutive_failures == 0 and state.retry_count == 0
    assert state.circuit_state is CircuitState.CLOSED
    assert state.health_status is HealthStatus.HEALTHY
    assert state.last_success_at == T0 and state.last_attempt_at == T0
    assert state.checkpoint == "h1" and state.cursor == "c1"
    assert state.avg_execution_ms == 120.0 and state.avg_events == 10.0
    assert state.next_run_at == T0 + timedelta(seconds=3600)
    assert state.created_at == T0  # created on first touch


def test_running_averages_across_runs():
    store = _store()
    run(
        store.update_after_run(
            "p", at=_at(0), execution_ms=100, events_discovered=10, policy=POLICY
        )
    )
    state = run(
        store.update_after_run(
            "p", at=_at(60), execution_ms=200, events_discovered=20, policy=POLICY
        )
    )
    assert state.total_runs == 2
    assert state.avg_execution_ms == 150.0  # (100 + 200) / 2
    assert state.avg_events == 15.0


# --------------------------- repeated failures ---------------------------


def test_repeated_failures_accumulate_and_degrade():
    store = _store()
    for i in range(2):  # below threshold (3)
        state = run(
            store.update_after_failure(
                "p", at=_at(i), error=f"boom{i}", execution_ms=50, policy=POLICY
            )
        )
    assert (state.consecutive_failures, state.total_failures, state.total_runs) == (2, 2, 2)
    assert state.retry_count == 2
    assert state.last_error == "boom1" and state.last_error_at == _at(1)
    assert state.circuit_state is CircuitState.CLOSED
    assert state.health_status is HealthStatus.DEGRADED
    # exponential backoff: retry 2 → 60 * 2^1 = 120s from the last attempt
    assert state.next_run_at == _at(1) + timedelta(seconds=120)


# --------------------------- circuit opening + recovery ---------------------------


def test_circuit_opens_at_threshold():
    store = _store()
    for i in range(3):  # hits threshold
        state = run(store.update_after_failure("p", at=_at(i), error="x", policy=POLICY))
    assert state.consecutive_failures == 3
    assert state.circuit_state is CircuitState.OPEN
    assert state.health_status is HealthStatus.FAILING
    # once open, next_run is pushed out by at least the cooldown
    assert state.next_run_at == _at(2) + timedelta(seconds=POLICY.circuit_cooldown_seconds)


def test_open_circuit_excluded_from_due_until_cooldown():
    store = _store()
    for i in range(3):
        run(store.update_after_failure("p", at=_at(i), error="x", policy=POLICY))
    # still cooling down
    assert "p" not in run(store.due_providers(_at(5)))
    # after the cooldown window it is due again (scheduler would probe = half-open)
    assert "p" in run(store.due_providers(_at(20)))


def test_success_after_failures_closes_circuit_and_resets_streak():
    store = _store()
    for i in range(3):
        run(store.update_after_failure("p", at=_at(i), error="x", policy=POLICY))
    state = run(
        store.update_after_run(
            "p", at=_at(20), execution_ms=100, events_discovered=5, policy=POLICY
        )
    )
    assert state.circuit_state is CircuitState.CLOSED
    assert state.consecutive_failures == 0 and state.retry_count == 0
    assert state.health_status is HealthStatus.HEALTHY
    assert (state.total_runs, state.total_successes, state.total_failures) == (4, 1, 3)
    assert state.last_error == "x"  # historical, preserved across the later success


def test_reset_circuit():
    store = _store()
    for i in range(3):
        run(store.update_after_failure("p", at=_at(i), error="x", policy=POLICY))
    run(store.reset_circuit("p", at=_at(20)))
    state = run(store.get_provider_state("p"))
    assert state.circuit_state is CircuitState.CLOSED
    assert state.consecutive_failures == 0 and state.retry_count == 0
    assert state.health_status is HealthStatus.HEALTHY


# --------------------------- checkpoint persistence ---------------------------


def test_checkpoint_and_cursor_persist_and_are_sticky():
    store = _store()
    run(
        store.update_after_run(
            "p",
            at=T0,
            execution_ms=10,
            events_discovered=1,
            checkpoint="hash-abc",
            cursor="page-2",
            policy=POLICY,
        )
    )
    # a later success that doesn't supply them keeps the prior values
    run(
        store.update_after_run("p", at=_at(60), execution_ms=10, events_discovered=1, policy=POLICY)
    )
    state = run(store.get_provider_state("p"))
    assert state.checkpoint == "hash-abc" and state.cursor == "page-2"


# --------------------------- due scheduling ---------------------------


def test_due_providers_orders_never_run_first_and_excludes_future():
    store = _store()
    run(store.save_provider_state(new_provider_state("p_new", at=T0)))  # never run → due
    # ran 2h ago; next_run = -2h + 1h = 1h ago → due
    run(
        store.update_after_run(
            "p_soon", at=_at(-120), execution_ms=1, events_discovered=1, policy=POLICY
        )
    )
    # ran now; next_run = +1h → not due
    run(
        store.update_after_run("p_later", at=T0, execution_ms=1, events_discovered=1, policy=POLICY)
    )

    due = run(store.due_providers(T0))
    assert due == ["p_new", "p_soon"]  # never-run first, then soonest; future excluded


def test_due_providers_respects_limit():
    store = _store()
    for name in ("a", "b", "c"):
        run(store.save_provider_state(new_provider_state(name, at=T0)))
    assert len(run(store.due_providers(T0, limit=2))) == 2


# --------------------------- provider disabling ---------------------------


def test_disable_and_enable_provider():
    store = _store()
    run(store.save_provider_state(new_provider_state("p", at=T0)))
    assert "p" in run(store.due_providers(T0))

    run(store.disable_provider("p", at=T0))
    assert "p" not in run(store.due_providers(T0))
    assert run(store.get_provider_state("p")).enabled is False

    run(store.enable_provider("p", at=T0))
    assert "p" in run(store.due_providers(T0))


# --------------------------- save / get / capabilities ---------------------------


def test_save_and_get_roundtrip_with_capabilities_and_extra():
    store = _store()
    original = ProviderState(
        provider_id="p",
        provider_version=3,
        capabilities={"pagination": True, "delta": False, "speakers": True},
        created_at=T0,
        updated_at=T0,
        extra={"note": "seed", "tier": 2},
    )
    run(store.save_provider_state(original))
    loaded = run(store.get_provider_state("p"))
    assert loaded.provider_version == 3
    assert loaded.capabilities == {"pagination": True, "delta": False, "speakers": True}
    assert loaded.extra == {"note": "seed", "tier": 2}


def test_get_missing_returns_none():
    assert run(_store().get_provider_state("nope")) is None


# --------------------------- restart persistence ---------------------------


def test_restart_persistence(tmp_path):
    path = str(tmp_path / "state.db")
    store = SQLiteProviderStateStore(path)
    run(
        store.update_after_run(
            "p",
            at=T0,
            execution_ms=100,
            events_discovered=7,
            checkpoint="ck",
            cursor="cur",
            policy=POLICY,
        )
    )
    run(store.update_after_failure("p", at=_at(60), error="later boom", policy=POLICY))
    run(store.close())

    reopened = SQLiteProviderStateStore(path)
    try:
        state = run(reopened.get_provider_state("p"))
        assert (state.total_runs, state.total_successes, state.total_failures) == (2, 1, 1)
        assert state.checkpoint == "ck" and state.cursor == "cur"
        assert state.last_error == "later boom"
        assert state.consecutive_failures == 1
        assert state.created_at == T0  # preserved across the reopen
    finally:
        run(reopened.close())


# --------------------------- concurrent updates ---------------------------


def test_concurrent_failures_never_lose_a_write():
    store = _store()
    run(store.save_provider_state(new_provider_state("p", at=T0)))

    async def hammer():
        await asyncio.gather(
            *(
                store.update_after_failure("p", at=_at(0), error="e", policy=POLICY)
                for _ in range(20)
            )
        )

    run(hammer())
    state = run(store.get_provider_state("p"))
    # Every concurrent read-modify-write is serialized under the lock → exact counts.
    assert state.total_failures == 20
    assert state.total_runs == 20
    assert state.consecutive_failures == 20


# --------------------------- health summary ---------------------------


def test_provider_health_summary():
    store = _store()
    run(
        store.update_after_run(
            "healthy1", at=T0, execution_ms=100, events_discovered=5, policy=POLICY
        )
    )
    for i in range(3):  # opens the circuit → failing
        run(store.update_after_failure("failing1", at=_at(i), error="x", policy=POLICY))
    run(store.update_after_failure("degraded1", at=T0, error="x", policy=POLICY))  # one failure
    run(store.save_provider_state(new_provider_state("unknown1", at=T0)))  # never run
    run(store.disable_provider("unknown1", at=T0))

    summary = run(store.provider_health_summary())
    assert summary.total == 4
    assert summary.enabled == 3 and summary.disabled == 1
    assert summary.by_health == {"healthy": 1, "failing": 1, "degraded": 1, "unknown": 1}
    assert summary.total_runs == 5  # 1 + 3 + 1 + 0
    assert summary.total_successes == 1
    assert summary.total_failures == 4
    assert summary.success_rate == 0.2
