"""Future expansion seams (Phase 8C) — INTERFACES ONLY, no implementations.

8C expands from raw HTML with no JavaScript. These abstractions mark where later phases plug in:
browser-rendered expansion for SPAs (the D2/8B blind spot), and public-social discovery (Discord/
Telegram/GitHub API enrichment — Phase 8D). Each raises `NotImplementedError`; none runs a browser
or a social API here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.discovery.expansion.extractor import Extraction
from app.discovery.fetch import FetchResult


class RenderedExtractor(ABC):
    """FUTURE: extract links from a JS-rendered DOM (SPAs that expose nothing in raw HTML).

    8C is HTML-only, so a React/Vue page that builds its links client-side yields little. A future
    renderer (still not in 8C's no-browser scope) would supply the post-hydration DOM here.
    """

    @abstractmethod
    async def extract_rendered(self, result: FetchResult) -> Extraction:  # pragma: no cover
        raise NotImplementedError("browser-rendered expansion is deferred (no browser in 8C)")


class SocialExpander(ABC):
    """FUTURE (Phase 8D): enrich Discord/Telegram/GitHub nodes via their public APIs."""

    @abstractmethod
    async def expand_social(self, url: str) -> list[str]:  # pragma: no cover
        raise NotImplementedError("public social discovery is Phase 8D — requires approval")
