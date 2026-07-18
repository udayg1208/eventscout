"""Phase 3D: the execution engine.

Network-free and deterministic (a FakeClock drives all time, FakeProviders stand in for
sources). Covers the queue, dispatcher (concurrency + failure isolation), rate limiter,
scheduler policy (due/future/priority/in-flight/rate-limit/permanent-failure/probe), and
the full engine (bootstrap, cycle execution, rescheduling, retry/backoff, circuit
open→probe→close, timeout, disable/enable, graceful shutdown, restart recovery, heartbeat,
metrics).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

from app.ingestion.plugin import ProviderPlugin
from app.ingestion.registry import ProviderRegistry
from app.models.event import Event, EventCategory
from app.providers.base import EventProvider
from app.scheduler import (
    AsyncioJobQueue,
    IngestionEngine,
    InProcessDispatcher,
    RateLimiter,
    Scheduler,
    execution_priority,
)
from app.scheduler.job import Job
from app.scheduler.scheduler import RetryStrategy
from app.storage.models import SearchCriteria
from app.storage.provider_state import CircuitState, ProviderState
from app.storage.sqlite_provider_state import SQLiteProviderStateStore
from app.storage.sqlite_repository import SQLiteEventRepository


def run(coro):
    return asyncio.run(coro)


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
TODAY = date(2026, 7, 15)


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


class FakeProvider(EventProvider):
    name = "fake"

    def __init__(self, events=None, *, fail=False, hang=0.0):
        self._events = events or []
        self.fail = fail
        self.hang = hang
        self.calls = 0

    async def search(self, query):
        self.calls += 1
        if self.hang:
            await asyncio.sleep(self.hang)
        if self.fail:
            raise RuntimeError("provider down")
        return list(self._events)


def _event(title="E"):
    return Event(
        title=title,
        url=f"https://x.example.com/{title.replace(' ', '-').lower()}",
        city="Bangalore",
        start_date=date(2026, 9, 1),
        category=EventCategory.MEETUP,
        provider="fake",
    )


def _fake_plugin(
    pid,
    provider=None,
    *,
    refresh=3600.0,
    volume=0,
    rate=0.0,
    max_attempts=1,
    timeout=5.0,
    failure_threshold=5,
    retry_backoff=2.0,
    circuit_cooldown=1800.0,
):
    return ProviderPlugin(
        id=pid,
        name=pid,
        version=1,
        provider=provider or FakeProvider([_event(f"{pid}-event")]),
        refresh_interval_seconds=refresh,
        expected_volume=volume,
        rate_limit_per_minute=rate,
        max_attempts=max_attempts,
        timeout_seconds=timeout,
        failure_threshold=failure_threshold,
        retry_backoff_seconds=retry_backoff,
        circuit_cooldown_seconds=circuit_cooldown,
    )


async def _seed(
    store, pid, *, next_run=None, enabled=True, consecutive=0, circuit=CircuitState.CLOSED
):
    await store.save_provider_state(
        ProviderState(
            provider_id=pid,
            enabled=enabled,
            next_run_at=next_run,
            consecutive_failures=consecutive,
            circuit_state=circuit,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def _engine(registry, repo, store, *, clock, **kw):
    return IngestionEngine(registry, repo, store, clock=clock, tick_interval_seconds=0.01, **kw)


# =========================== queue ===========================


def test_asyncio_job_queue_put_get_join():
    async def scenario():
        q = AsyncioJobQueue()
        await q.put(Job("a", NOW))
        size = q.qsize()
        job = await q.get()
        q.task_done()
        await q.join()
        return size, job.provider_id

    size, pid = run(scenario())
    assert size == 1 and pid == "a"


# =========================== dispatcher ===========================


def test_dispatcher_processes_all_and_isolates_failures():
    handled = []

    async def handler(job):
        if job.provider_id == "bad":
            raise RuntimeError("boom")
        handled.append(job.provider_id)

    async def scenario():
        d = InProcessDispatcher(handler, concurrency=2)
        await d.start()
        for pid in ("a", "bad", "b"):
            await d.submit(Job(pid, NOW))
        await d.drain()
        await d.shutdown()

    run(scenario())
    assert set(handled) == {"a", "b"}  # 'bad' isolated; others still processed


def test_dispatcher_respects_global_concurrency():
    active = 0
    peak = 0

    async def handler(_job):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1

    async def scenario():
        d = InProcessDispatcher(handler, concurrency=2)
        await d.start()
        for i in range(6):
            await d.submit(Job(f"p{i}", NOW))
        await d.drain()
        await d.shutdown()

    run(scenario())
    assert peak <= 2  # never more than the global limit run at once


# =========================== policy units ===========================


def test_rate_limiter():
    rl = RateLimiter()
    assert rl.allow("p", now=NOW, min_interval_seconds=60)
    rl.record("p", now=NOW)
    assert not rl.allow("p", now=NOW + timedelta(seconds=30), min_interval_seconds=60)
    assert rl.allow("p", now=NOW + timedelta(seconds=61), min_interval_seconds=60)
    assert rl.allow("p", now=NOW, min_interval_seconds=0)  # disabled


def test_execution_priority_from_metadata():
    frequent = _fake_plugin("f", refresh=60, volume=1)
    rare = _fake_plugin("r", refresh=3600, volume=1)
    assert execution_priority(frequent) < execution_priority(rare)  # fresher first
    high = _fake_plugin("h", refresh=100, volume=50)
    low = _fake_plugin("l", refresh=100, volume=5)
    assert execution_priority(high) < execution_priority(low)  # tie → more volume first


def test_retry_strategy_permanent_failure():
    strat = RetryStrategy(max_consecutive_failures=3)
    assert not strat.is_permanent_failure(ProviderState("p", consecutive_failures=2))
    assert strat.is_permanent_failure(ProviderState("p", consecutive_failures=3))
    assert not RetryStrategy().is_permanent_failure(ProviderState("p", consecutive_failures=99))


# =========================== scheduler ===========================


def _scheduler(store, *plugins, rate_limiter=None, retry=None):
    return Scheduler(
        ProviderRegistry(list(plugins)),
        store,
        rate_limiter=rate_limiter or RateLimiter(),
        retry_strategy=retry or RetryStrategy(),
    )


def test_scheduler_finds_due_and_ignores_future():
    async def scenario():
        store = SQLiteProviderStateStore()
        await _seed(store, "never", next_run=None)
        await _seed(store, "past", next_run=NOW - timedelta(minutes=1))
        await _seed(store, "future", next_run=NOW + timedelta(hours=1))
        sched = _scheduler(
            store, _fake_plugin("never"), _fake_plugin("past"), _fake_plugin("future")
        )
        jobs = await sched.due_jobs(now=NOW, exclude=set())
        return {j.provider_id for j in jobs}

    assert run(scenario()) == {"never", "past"}


def test_scheduler_orders_by_priority():
    async def scenario():
        store = SQLiteProviderStateStore()
        await _seed(store, "slow", next_run=None)
        await _seed(store, "fast", next_run=None)
        sched = _scheduler(
            store, _fake_plugin("slow", refresh=3600), _fake_plugin("fast", refresh=60)
        )
        jobs = await sched.due_jobs(now=NOW, exclude=set())
        return [j.provider_id for j in jobs]

    assert run(scenario()) == ["fast", "slow"]


def test_scheduler_excludes_inflight():
    async def scenario():
        store = SQLiteProviderStateStore()
        await _seed(store, "a", next_run=None)
        await _seed(store, "b", next_run=None)
        sched = _scheduler(store, _fake_plugin("a"), _fake_plugin("b"))
        jobs = await sched.due_jobs(now=NOW, exclude={"a"})
        return {j.provider_id for j in jobs}

    assert run(scenario()) == {"b"}


def test_scheduler_respects_rate_limit():
    async def scenario():
        store = SQLiteProviderStateStore()
        await _seed(store, "p", next_run=None)
        rl = RateLimiter()
        rl.record("p", now=NOW)  # just ran
        sched = _scheduler(store, _fake_plugin("p", rate=60), rate_limiter=rl)  # 1/s min interval
        blocked = await sched.due_jobs(now=NOW + timedelta(seconds=0.5), exclude=set())
        allowed = await sched.due_jobs(now=NOW + timedelta(seconds=2), exclude=set())
        return len(blocked), len(allowed)

    blocked, allowed = run(scenario())
    assert blocked == 0 and allowed == 1


def test_scheduler_auto_disables_permanent_failure():
    async def scenario():
        store = SQLiteProviderStateStore()
        await _seed(store, "p", next_run=None, consecutive=5)
        sched = _scheduler(
            store, _fake_plugin("p"), retry=RetryStrategy(max_consecutive_failures=3)
        )
        jobs = await sched.due_jobs(now=NOW, exclude=set())
        return len(jobs), (await store.get_provider_state("p")).enabled

    n, enabled = run(scenario())
    assert n == 0 and enabled is False


def test_scheduler_flags_open_circuit_as_probe():
    async def scenario():
        store = SQLiteProviderStateStore()
        await _seed(store, "p", next_run=NOW - timedelta(seconds=1), circuit=CircuitState.OPEN)
        sched = _scheduler(store, _fake_plugin("p"))
        jobs = await sched.due_jobs(now=NOW, exclude=set())
        return jobs

    jobs = run(scenario())
    assert len(jobs) == 1 and jobs[0].is_probe is True


# =========================== engine ===========================


def test_engine_bootstrap_and_cycle_executes_all():
    async def scenario():
        clock = FakeClock(NOW)
        repo, store = SQLiteEventRepository(), SQLiteProviderStateStore()
        registry = ProviderRegistry([_fake_plugin("a"), _fake_plugin("b")])
        engine = _engine(registry, repo, store, clock=clock, concurrency=2)
        enqueued = await engine.run_cycle()
        await engine.shutdown()
        return enqueued, await repo.count(SearchCriteria()), await store.get_provider_state("a")

    enqueued, count, state = run(scenario())
    assert enqueued == 2 and count == 2
    assert state.total_runs == 1 and state.total_successes == 1 and state.checkpoint is not None


def test_engine_idle_when_nothing_due():
    async def scenario():
        clock = FakeClock(NOW)
        repo, store = SQLiteEventRepository(), SQLiteProviderStateStore()
        engine = _engine(ProviderRegistry([_fake_plugin("a")]), repo, store, clock=clock)
        await engine.run_cycle()  # a runs → next_run = NOW + 3600
        second = await engine.run_cycle()  # same clock → not due
        await engine.shutdown()
        return second

    assert run(scenario()) == 0


def test_engine_reschedules_after_refresh_interval():
    async def scenario():
        clock = FakeClock(NOW)
        repo, store = SQLiteEventRepository(), SQLiteProviderStateStore()
        engine = _engine(
            ProviderRegistry([_fake_plugin("a", refresh=3600)]), repo, store, clock=clock
        )
        await engine.run_cycle()
        clock.advance(3601)
        again = await engine.run_cycle()
        await engine.shutdown()
        return again, (await store.get_provider_state("a")).total_runs

    again, runs = run(scenario())
    assert again == 1 and runs == 2


def test_engine_isolates_provider_failures():
    async def scenario():
        clock = FakeClock(NOW)
        repo, store = SQLiteEventRepository(), SQLiteProviderStateStore()
        registry = ProviderRegistry(
            [_fake_plugin("good"), _fake_plugin("bad", provider=FakeProvider(fail=True))]
        )
        engine = _engine(registry, repo, store, clock=clock, concurrency=2)
        await engine.run_cycle()
        await engine.shutdown()
        good = await store.get_provider_state("good")
        bad = await store.get_provider_state("bad")
        return await repo.count(SearchCriteria()), good, bad

    count, good, bad = run(scenario())
    assert count == 1  # only the good provider's event
    assert good.total_successes == 1 and good.total_failures == 0
    assert bad.total_failures == 1 and bad.consecutive_failures == 1


def test_engine_retries_failed_provider_after_backoff():
    async def scenario():
        clock = FakeClock(NOW)
        repo, store = SQLiteEventRepository(), SQLiteProviderStateStore()
        bad = _fake_plugin("bad", provider=FakeProvider(fail=True), retry_backoff=1)
        engine = _engine(ProviderRegistry([bad]), repo, store, clock=clock)
        await engine.run_cycle()  # fails → next_run = NOW + 1s
        immediate = await engine.run_cycle()  # not due yet
        clock.advance(2)
        jobs = await engine._scheduler.due_jobs(now=clock(), exclude=set())
        await engine.shutdown()
        return immediate, jobs

    immediate, jobs = run(scenario())
    assert immediate == 0
    assert len(jobs) == 1 and jobs[0].is_retry is True


def test_engine_circuit_opens_probes_and_recovers():
    async def scenario():
        clock = FakeClock(NOW)
        repo, store = SQLiteEventRepository(), SQLiteProviderStateStore()
        source = FakeProvider([_event("recovered")], fail=True)
        plugin = _fake_plugin(
            "flaky", provider=source, failure_threshold=2, retry_backoff=1, circuit_cooldown=100
        )
        engine = _engine(ProviderRegistry([plugin]), repo, store, clock=clock)

        await engine.run_cycle()  # fail 1 (next_run +1s)
        clock.advance(2)
        await engine.run_cycle()  # fail 2 → circuit OPEN (next_run +100s)
        opened = (await store.get_provider_state("flaky")).circuit_state

        clock.advance(50)
        during_cooldown = await engine.run_cycle()  # still cooling down → not due

        clock.advance(60)  # past cooldown
        source.fail = False  # provider now recovers
        await engine.run_cycle()  # probe → success → circuit closes
        recovered = await store.get_provider_state("flaky")
        metrics = await engine.metrics()
        await engine.shutdown()
        return opened, during_cooldown, recovered, metrics

    opened, during_cooldown, recovered, metrics = run(scenario())
    assert opened is CircuitState.OPEN
    assert during_cooldown == 0
    assert recovered.circuit_state is CircuitState.CLOSED
    assert recovered.total_successes == 1
    assert metrics["probes"] >= 1


def test_engine_handles_timeout_as_failure():
    async def scenario():
        clock = FakeClock(NOW)
        repo, store = SQLiteEventRepository(), SQLiteProviderStateStore()
        slow = _fake_plugin("slow", provider=FakeProvider([_event("x")], hang=0.5), timeout=0.01)
        engine = _engine(ProviderRegistry([slow]), repo, store, clock=clock)
        await engine.run_cycle()
        await engine.shutdown()
        return await store.get_provider_state("slow")

    state = run(scenario())
    assert state.total_failures == 1


def test_engine_disable_and_enable_provider():
    async def scenario():
        clock = FakeClock(NOW)
        repo, store = SQLiteEventRepository(), SQLiteProviderStateStore()
        engine = _engine(ProviderRegistry([_fake_plugin("a")]), repo, store, clock=clock)
        await engine.start()
        await store.disable_provider("a", at=NOW)
        while_disabled = await engine.run_cycle()
        await store.enable_provider("a", at=NOW)
        while_enabled = await engine.run_cycle()
        await engine.shutdown()
        return while_disabled, while_enabled

    disabled, enabled = run(scenario())
    assert disabled == 0 and enabled == 1


def test_engine_graceful_shutdown_finishes_inflight_work():
    async def scenario():
        clock = FakeClock(NOW)
        repo, store = SQLiteEventRepository(), SQLiteProviderStateStore()
        engine = _engine(ProviderRegistry([_fake_plugin("a")]), repo, store, clock=clock)
        await engine.start()
        await engine.tick()  # enqueue, do NOT drain
        await engine.shutdown(graceful=True)  # must finish the enqueued job
        return await store.get_provider_state("a")

    state = run(scenario())
    assert state is not None and state.total_runs == 1


def test_engine_restart_recovery(tmp_path):
    async def scenario():
        clock = FakeClock(NOW)
        repo_path = str(tmp_path / "events.db")
        state_path = str(tmp_path / "state.db")
        registry = ProviderRegistry([_fake_plugin("a", refresh=3600)])

        repo1, store1 = SQLiteEventRepository(repo_path), SQLiteProviderStateStore(state_path)
        engine1 = _engine(registry, repo1, store1, clock=clock)
        await engine1.run_cycle()  # a runs; next_run = NOW + 3600 (persisted)
        await engine1.shutdown()
        await repo1.close()
        await store1.close()

        # restart over the same durable stores, same clock
        repo2, store2 = SQLiteEventRepository(repo_path), SQLiteProviderStateStore(state_path)
        engine2 = _engine(registry, repo2, store2, clock=clock)
        created = await engine2.bootstrap()  # idempotent — 'a' already exists
        again = await engine2.run_cycle()  # not due (persisted next_run in the future)
        state = await store2.get_provider_state("a")
        catalog = await repo2.count(SearchCriteria())
        await engine2.shutdown()
        await repo2.close()
        await store2.close()
        return created, again, state.total_runs, catalog

    created, again, runs, catalog = run(scenario())
    assert created == 0  # bootstrap did not recreate — state persisted
    assert again == 0  # not due after restart — schedule persisted
    assert runs == 1 and catalog == 1  # run count + catalog survived the restart


def test_engine_heartbeat_and_metrics():
    async def scenario():
        clock = FakeClock(NOW)
        repo, store = SQLiteEventRepository(), SQLiteProviderStateStore()
        registry = ProviderRegistry(
            [_fake_plugin("good"), _fake_plugin("bad", provider=FakeProvider(fail=True))]
        )
        engine = _engine(registry, repo, store, clock=clock, concurrency=3)
        await engine.run_cycle()
        hb = engine.heartbeat()
        metrics = await engine.metrics()
        await engine.shutdown()
        return hb, metrics

    hb, metrics = run(scenario())
    assert hb["tick_count"] >= 1 and hb["workers_alive"] == 3
    assert metrics["providers_executed"] == 2
    assert metrics["successes"] == 1 and metrics["failures"] == 1
    assert metrics["success_rate"] == 0.5
    assert metrics["events_ingested"] >= 1
    assert "provider_health" in metrics
