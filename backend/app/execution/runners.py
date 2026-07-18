"""Real stage runners (Phase 10A) — the live implementations of the orchestrator's StageRunner seam.

Each factory returns an async `StageContext → StageOutcome` that calls a real engine and maps its
report into the counts the orchestrator + metrics track. The search runner queries a real provider;
the expansion runner crawls real URLs; the social and rendered runners fetch the seed pages once via
the shared `PageFetcher` and hand the real HTML to the extraction engines. All candidates flow into
the `VerifyingInbox`. This is the whole point of the phase — wiring, not new abstraction.
"""

from __future__ import annotations

from app.discovery.rendered import RenderedPage
from app.execution.fetching import PageFetcher
from app.execution.metrics import ExecutionMetrics
from app.orchestrator.models import StageContext, StageHealth, StageOutcome, StageRunner


def search_runner(engine, *, spec=None) -> StageRunner:
    """WebDiscoveryEngine.run(spec) — real search provider → inbox; seeds cascade to expansion."""

    async def run(ctx: StageContext) -> StageOutcome:
        report = await (engine.run(spec) if spec is not None else engine.run())
        health = (
            StageHealth.DEGRADED if getattr(report, "provider_errors", 0) else StageHealth.HEALTHY
        )
        return StageOutcome(
            health=health,
            discovered=getattr(report, "inserted", 0),
            duplicates=getattr(report, "skipped_known", 0),
            produced_seeds=list(ctx.seeds),
        )

    return run


def expansion_runner(engine, metrics: ExecutionMetrics, *, max_pages: int = 25) -> StageRunner:
    """ExpansionEngine.expand(seeds) — real polite crawl (robots + budget + freshness)."""

    async def run(ctx: StageContext) -> StageOutcome:
        report = await engine.expand(list(ctx.seeds), max_pages=max_pages)
        metrics.record_pages(crawled=report.pages_fetched, skipped=report.pages_skipped)
        return StageOutcome(
            discovered=report.candidates_inserted,
            pages=report.pages_fetched,
            produced_seeds=list(ctx.seeds),  # the known URLs → social/rendered extraction
        )

    return run


def social_runner(engine, page_fetcher: PageFetcher) -> StageRunner:
    """Fetch the seed pages once, hand real (url, html) to SocialDiscoveryEngine.discover."""

    async def run(ctx: StageContext) -> StageOutcome:
        pages = await page_fetcher.fetch_many(list(ctx.seeds))
        report = await engine.discover([(p.final_url, p.html) for p in pages])
        return StageOutcome(
            discovered=report.inserted,
            rejected=report.rejected,
            pages=len(pages),
        )

    return run


def rendered_runner(engine, page_fetcher: PageFetcher) -> StageRunner:
    """Fetch the seed pages, hand real HTML to RenderedDiscoveryEngine.discover (hydration/APIs)."""

    async def run(ctx: StageContext) -> StageOutcome:
        pages = await page_fetcher.fetch_many(list(ctx.seeds))
        rendered = [RenderedPage(url=p.final_url, html=p.html) for p in pages]
        report = await engine.discover(rendered)
        return StageOutcome(
            discovered=report.candidates_inserted,
            pages=report.pages,
            ai_calls=report.provider_candidates,
        )

    return run
