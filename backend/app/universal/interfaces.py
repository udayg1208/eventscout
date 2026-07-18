"""Future seams (Phase 10B) — INTERFACES ONLY, no implementations.

10B reads served bytes and never executes JavaScript. `BrowserRenderer` marks where a later phase
would render a pure-runtime SPA (execute its JS to obtain the hydrated DOM) and feed that HTML back
into the same engine — the one class of page byte-level extraction cannot see. It raises
`NotImplementedError` and is not used in 10B: no browser, no Playwright, no Selenium.
"""

from __future__ import annotations

from abc import abstractmethod


class BrowserRenderer:
    """FUTURE: execute a page's JS to obtain the hydrated DOM, then hand the HTML to the engine.

    Out of 10B's no-browser scope; this is the seam a headless renderer would implement so the
    universal engine gains SPA reach without any change to its extractors."""

    @abstractmethod
    async def render(self, url: str, html: str) -> str:  # pragma: no cover
        raise NotImplementedError("browser rendering is deferred — 10B is byte-level only")
