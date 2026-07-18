"""Real Discovery Execution (Phase 10A).

Wires the existing discovery engines (D1–D4, Web, Expansion, Social, Rendered) to the real internet
and drives them through the 9A orchestrator, so the platform autonomously discovers new event feeds
from public web content. Additive; reuses every engine unchanged. Public content only, robots
respected, discovery only — nothing onboarded, the catalog is never touched. No browser, no JS
execution, no auth.
"""

from __future__ import annotations

from app.execution.engine import ExecutionReport, RealDiscoveryPipeline
from app.execution.fetching import FetchedPage, FetchStats, PageFetcher
from app.execution.metrics import DailyMetrics, ExecutionMetrics
from app.execution.providers import active_provider_name, build_web_provider
from app.execution.runners import (
    expansion_runner,
    rendered_runner,
    search_runner,
    social_runner,
)
from app.execution.seeds import (
    DEFAULT_SEEDS,
    PRODUCTION_SEEDS,
    SEED_LIST_VERSION,
    ProductionSeedList,
    Seed,
    SeedCategory,
)
from app.execution.verification import SourceVerifier, VerificationResult, VerifyingInbox

__all__ = [
    "RealDiscoveryPipeline",
    "ExecutionReport",
    "PageFetcher",
    "FetchedPage",
    "FetchStats",
    "ExecutionMetrics",
    "DailyMetrics",
    "build_web_provider",
    "active_provider_name",
    "search_runner",
    "expansion_runner",
    "social_runner",
    "rendered_runner",
    "SourceVerifier",
    "VerifyingInbox",
    "VerificationResult",
    "ProductionSeedList",
    "Seed",
    "SeedCategory",
    "PRODUCTION_SEEDS",
    "DEFAULT_SEEDS",
    "SEED_LIST_VERSION",
]
