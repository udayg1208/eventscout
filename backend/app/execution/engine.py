"""Real discovery execution pipeline (Phase 10A) — wire the engines to the live web + orchestrator.

Builds the real collaborators (HTTP fetcher, search provider, robots cache, page fetcher), wraps the
Discovery Inbox in a `VerifyingInbox`, constructs the four discovery engines pointing at it, and
registers real `StageRunner`s with a 9A `OrchestratorEngine` over a focused
Search → Expansion → Social → Rendered pipeline. Reliability — retries, checkpoint resume, graceful
shutdown, partial restart — is the orchestrator's, reused unchanged. `run_cycle()` seeds from the
versioned production seed list and runs a real bounded cycle, returning an `ExecutionReport`
with daily metrics. Public content only; robots respected; discovery only; nothing onboarded.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from app.discovery import DiscoveryInbox, DiscoveryStatus, InMemoryDiscoveryInbox
from app.discovery.expansion import ExpansionEngine
from app.discovery.fetch import Fetcher, HttpxFetcher
from app.discovery.rendered import RenderedDiscoveryEngine
from app.discovery.robots import RobotsCache
from app.discovery.search import QuerySpec
from app.discovery.social import SocialDiscoveryEngine
from app.discovery.web import (
    PoliteFetcher,
    RateLimiter,
    SearchCache,
    WebDiscoveryEngine,
    WebSearchProvider,
)
from app.execution.fetching import PageFetcher
from app.execution.metrics import DailyMetrics, ExecutionMetrics
from app.execution.providers import build_web_provider
from app.execution.runners import (
    expansion_runner,
    rendered_runner,
    search_runner,
    social_runner,
)
from app.execution.seeds import DEFAULT_SEEDS, ProductionSeedList
from app.execution.verification import SourceVerifier, VerifyingInbox
from app.orchestrator import (
    BudgetKind,
    OrchestratorEngine,
    OrchestratorReport,
    OrchestratorStore,
    Pipeline,
    Schedule,
    ScheduleKind,
    StageName,
    StageSpec,
    Trigger,
)

S = StageName

_DEFAULT_BUDGETS = {
    BudgetKind.SEARCH: 50,
    BudgetKind.CRAWL: 400,
    BudgetKind.PAGE: 400,
    BudgetKind.AI: 100,
    BudgetKind.PROVIDER: 20,
    BudgetKind.DEPTH: 4,
}


def _discovery_pipeline() -> Pipeline:
    """A focused 4-stage discovery pipeline: Search → Expansion → Social/Rendered → Inbox."""
    return Pipeline(
        [
            StageSpec(
                name=S.SEARCH_DISCOVERY,
                # hourly: runs once at the top of a cycle, then yields to the backlog stages
                schedule=Schedule(kind=ScheduleKind.HOURLY),
                priority=9.0,
                trigger=Trigger.SCHEDULE,
                budgets={BudgetKind.SEARCH: 20, BudgetKind.PAGE: 40},
                produces_for=[S.EXPANSION],
            ),
            StageSpec(
                name=S.EXPANSION,
                schedule=Schedule(kind=ScheduleKind.CONTINUOUS),
                priority=8.0,
                trigger=Trigger.BACKLOG,
                budgets={BudgetKind.CRAWL: 100, BudgetKind.PAGE: 100, BudgetKind.DEPTH: 2},
                produces_for=[S.SOCIAL_DISCOVERY, S.RENDERED_DISCOVERY],
                timeout_seconds=120.0,
            ),
            StageSpec(
                name=S.SOCIAL_DISCOVERY,
                schedule=Schedule(kind=ScheduleKind.CONTINUOUS),
                priority=7.0,
                trigger=Trigger.BACKLOG,
                budgets={BudgetKind.PAGE: 60},
                timeout_seconds=120.0,
            ),
            StageSpec(
                name=S.RENDERED_DISCOVERY,
                schedule=Schedule(kind=ScheduleKind.CONTINUOUS),
                priority=7.0,
                trigger=Trigger.BACKLOG,
                budgets={BudgetKind.PAGE: 60, BudgetKind.AI: 40},
                timeout_seconds=120.0,
            ),
        ]
    )


@dataclass
class ExecutionReport:
    provider: str
    seed_version: str
    orchestrator: OrchestratorReport
    metrics: DailyMetrics
    inbox_total: int
    inbox_new: int

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "seed_version": self.seed_version,
            "inbox_total": self.inbox_total,
            "inbox_new": self.inbox_new,
            "metrics": self.metrics.as_dict(),
            "orchestrator": {
                "cycles": self.orchestrator.cycles,
                "stages_run": self.orchestrator.stages_run,
                "dead_lettered": self.orchestrator.dead_lettered,
            },
        }


class RealDiscoveryPipeline:
    def __init__(
        self,
        *,
        inbox: DiscoveryInbox | None = None,
        fetcher: Fetcher | None = None,
        web_provider: WebSearchProvider | None = None,
        polite_fetcher: PoliteFetcher | None = None,
        seeds: ProductionSeedList | None = None,
        spec: QuerySpec | None = None,
        orchestrator_store: OrchestratorStore | None = None,
        budgets: dict[BudgetKind, int] | None = None,
        respect_robots: bool = True,
        min_relevance: float = 0.15,
        revisit_hours: float = 24.0,
        max_pages: int = 25,
        env: Mapping[str, str] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._clock = clock
        self._seeds = seeds or DEFAULT_SEEDS
        self._spec = spec
        self.metrics = ExecutionMetrics()

        # real collaborators (all injectable for tests: pass a StaticFetcher / StaticProvider)
        self._fetcher = fetcher or HttpxFetcher()
        self._provider = web_provider or build_web_provider(
            polite_fetcher or PoliteFetcher(), env=env
        )
        robots = RobotsCache(self._fetcher) if respect_robots else None

        # verification gate — every candidate validated before the real inbox
        base_inbox = inbox or InMemoryDiscoveryInbox()
        verifier = SourceVerifier(
            robots=robots, min_relevance=min_relevance, revisit_hours=revisit_hours, clock=clock
        )
        self._inbox: DiscoveryInbox = VerifyingInbox(
            base_inbox, verifier, on_result=self.metrics.record_verification
        )

        # shared polite page fetch for the processor engines
        self._page_fetcher = PageFetcher(
            self._fetcher, robots=robots, respect_robots=respect_robots
        )

        # the real engines — all upsert through the verifying inbox
        self._web = WebDiscoveryEngine(
            self._provider,
            self._inbox,
            cache=SearchCache(clock=clock),
            rate_limiter=RateLimiter(),
            clock=clock,
        )
        self._expansion = ExpansionEngine(self._fetcher, self._inbox, clock=clock)
        self._social = SocialDiscoveryEngine(self._inbox, clock=clock)
        self._rendered = RenderedDiscoveryEngine(self._inbox, clock=clock)

        # orchestrator: real runners over the focused discovery pipeline (reliability reused)
        runners = {
            S.SEARCH_DISCOVERY: search_runner(self._web, spec=spec),
            S.EXPANSION: expansion_runner(self._expansion, self.metrics, max_pages=max_pages),
            S.SOCIAL_DISCOVERY: social_runner(self._social, self._page_fetcher),
            S.RENDERED_DISCOVERY: rendered_runner(self._rendered, self._page_fetcher),
        }
        self.orchestrator = OrchestratorEngine(
            _discovery_pipeline(),
            runners,
            store=orchestrator_store,
            budgets=budgets or dict(_DEFAULT_BUDGETS),
            clock=clock,
        )

    @property
    def inbox(self) -> DiscoveryInbox:
        return self._inbox

    @property
    def page_fetcher(self) -> PageFetcher:
        return self._page_fetcher

    def seed(self, urls: list[str] | None = None) -> None:
        """Enqueue seed URLs as backlog for the crawl + extraction stages."""
        targets = urls if urls is not None else self._seeds.urls()
        for stage in (S.EXPANSION, S.SOCIAL_DISCOVERY, S.RENDERED_DISCOVERY):
            self.orchestrator.seed(stage, targets)

    async def run_cycle(
        self, *, max_cycles: int = 12, seed_urls: list[str] | None = None
    ) -> ExecutionReport:
        self.seed(seed_urls)
        report = await self.orchestrator.run(max_cycles=max_cycles, stop_when_idle=True)
        # reconcile page metrics from the shared page fetcher (social + rendered)
        st = self._page_fetcher.stats
        self.metrics.record_pages(
            crawled=st.fetched, skipped=st.skipped_robots + st.skipped_error, cost_bytes=st.bytes
        )
        daily = self.metrics.snapshot(date=self._clock().date().isoformat())
        return ExecutionReport(
            provider=self._provider.name,
            seed_version=self._seeds.version,
            orchestrator=report,
            metrics=daily,
            inbox_total=await self._inbox.count(),
            inbox_new=await self._inbox.count(status=DiscoveryStatus.NEW),
        )

    async def resume(self) -> bool:
        return await self.orchestrator.resume_from_store()

    def stop(self) -> None:
        self.orchestrator.stop()
