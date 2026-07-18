"""Phase 3D live verification (not a test).

Runs the real execution engine over the seven real providers plus one always-failing
provider (to exercise retry/failure live), on durable file-backed stores, using a
controllable clock so rescheduling/retry can be demonstrated without waiting hours. Shows:
cycle execution, provider-state updates, idle ticking (scheduler sleeps), retry, live
metrics + heartbeat, the run_forever loop, graceful shutdown, and restart recovery.

Run (from backend/):  PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.m3d_scheduler
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.ingestion.plugin import ProviderPlugin  # noqa: E402
from app.ingestion.registry import ProviderRegistry, build_registry  # noqa: E402
from app.models.search import SearchQuery  # noqa: E402
from app.providers.base import EventProvider  # noqa: E402
from app.scheduler import IngestionEngine  # noqa: E402
from app.storage.models import SearchCriteria  # noqa: E402
from app.storage.sqlite_provider_state import SQLiteProviderStateStore  # noqa: E402
from app.storage.sqlite_repository import SQLiteEventRepository  # noqa: E402


class FailingProvider(EventProvider):
    name = "flaky-demo"

    async def search(self, query: SearchQuery):
        raise RuntimeError("simulated outage")


class Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def registry_with_failing_demo() -> ProviderRegistry:
    plugins = build_registry().all()
    plugins.append(
        ProviderPlugin(
            id="flaky-demo",
            name="Flaky Demo",
            version=1,
            provider=FailingProvider(),
            refresh_interval_seconds=3600,
            failure_threshold=3,
            retry_backoff_seconds=5,
            circuit_cooldown_seconds=60,
        )
    )
    return ProviderRegistry(plugins)


def _show(label: str, data: dict) -> None:
    print(f"{label}: {json.dumps(data, default=str)}")


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="m3d_"))
    repo_path, state_path = str(tmp / "events.db"), str(tmp / "state.db")
    clock = Clock(datetime.now(UTC))
    registry = registry_with_failing_demo()

    repo = SQLiteEventRepository(repo_path)
    state = SQLiteProviderStateStore(state_path)
    engine = IngestionEngine(registry, repo, state, clock=clock, concurrency=4, tick_interval_seconds=0.05)

    print("=== CYCLE 1 — one scheduling pass over all providers ===")
    enqueued = await engine.run_cycle()
    catalog = await repo.count(SearchCriteria())
    print(f"enqueued={enqueued}  catalog_active={catalog}")
    _show("metrics", await engine.metrics())
    _show("heartbeat", engine.heartbeat())

    print("\n=== PROVIDER STATE (after cycle 1) ===")
    for pid in registry.ids():
        s = await state.get_provider_state(pid)
        nxt = s.next_run_at.strftime("%H:%M:%S") if s.next_run_at else "-"
        print(f"  {pid:12s} runs={s.total_runs} ok={s.total_successes} fail={s.total_failures} "
              f"{s.health_status.value:8s} circuit={s.circuit_state.value:6s} next={nxt}")

    print("\n=== CYCLE 2 — nothing due yet (scheduler sleeps) ===")
    print(f"enqueued={await engine.run_cycle()}  (queue drains to 0)")

    print("\n=== RETRY — advance clock past the failing provider's backoff ===")
    clock.advance(6)  # flaky-demo backoff was 5s
    enqueued = await engine.run_cycle()
    flaky = await state.get_provider_state("flaky-demo")
    print(f"enqueued={enqueued}  flaky-demo: fail={flaky.total_failures} "
          f"consecutive={flaky.consecutive_failures} circuit={flaky.circuit_state.value}")
    _show("metrics", await engine.metrics())

    print("\n=== RUN_FOREVER — idle ticking then graceful shutdown ===")
    loop_task = asyncio.create_task(engine.run_forever())
    await asyncio.sleep(0.25)  # a few idle ticks (nothing due on the frozen clock)
    await engine.shutdown(graceful=True)
    await loop_task
    hb = engine.heartbeat()
    print(f"loop stopped: ticks={hb['tick_count']} uptime={hb['uptime_seconds']}s  shutdown OK")
    await repo.close()
    await state.close()

    print("\n=== RESTART — reopen durable stores, resume cleanly ===")
    repo2 = SQLiteEventRepository(repo_path)
    state2 = SQLiteProviderStateStore(state_path)
    engine2 = IngestionEngine(registry, repo2, state2, clock=clock, concurrency=4)
    created = await engine2.bootstrap()
    due_after_restart = await engine2.run_cycle()
    catalog2 = await repo2.count(SearchCriteria())
    print(f"bootstrap_new={created} (0 = state persisted)  due_after_restart={due_after_restart} "
          f"(0 = schedule persisted)  catalog_active={catalog2}")
    summary = await state2.provider_health_summary()
    print(f"fleet health={summary.by_health} runs={summary.total_runs} "
          f"ok={summary.total_successes} fail={summary.total_failures}")
    await engine2.shutdown()
    await repo2.close()
    await state2.close()


if __name__ == "__main__":
    asyncio.run(main())
