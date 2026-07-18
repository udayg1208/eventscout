"""Real search-provider selection (Phase 10A) — env-driven, reuses the existing web providers.

Lifts the provider-selection logic that previously lived only in the 8B spike into application code
(additive — no engine changes). Picks the first provider whose credentials are present in the
environment; falls back to the zero-key DuckDuckGo HTML provider so the pipeline always has a live
real search source. Nothing here fetches — it just wires a `PoliteFetcher` into the right provider.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from app.discovery.web import (
    BingWebSearchProvider,
    DuckDuckGoProvider,
    GoogleProgrammableSearchProvider,
    PoliteFetcher,
    RobotsGate,
    SearchProviderConfig,
    SerpApiSearchProvider,
    WebSearchProvider,
)


def active_provider_name(env: Mapping[str, str] | None = None) -> str:
    env = env if env is not None else os.environ
    if env.get("GOOGLE_API_KEY") and env.get("GOOGLE_CX"):
        return "google"
    if env.get("BING_API_KEY"):
        return "bing"
    if env.get("SERPAPI_KEY"):
        return "serpapi"
    return "duckduckgo"


def build_web_provider(
    fetcher: PoliteFetcher, *, env: Mapping[str, str] | None = None
) -> WebSearchProvider:
    """Select a real `WebSearchProvider` from the environment (DuckDuckGo when no key is set)."""
    env = env if env is not None else os.environ
    name = active_provider_name(env)
    if name == "google":
        cfg = SearchProviderConfig(api_key=env["GOOGLE_API_KEY"], engine_id=env["GOOGLE_CX"])
        return GoogleProgrammableSearchProvider(cfg, fetcher=fetcher)
    if name == "bing":
        return BingWebSearchProvider(
            SearchProviderConfig(api_key=env["BING_API_KEY"]), fetcher=fetcher
        )
    if name == "serpapi":
        return SerpApiSearchProvider(
            SearchProviderConfig(api_key=env["SERPAPI_KEY"]), fetcher=fetcher
        )
    return DuckDuckGoProvider(fetcher=fetcher, mode="html", robots=RobotsGate(fetcher))
