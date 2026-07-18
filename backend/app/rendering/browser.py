"""Headless-browser renderer — the JavaScript-executing replacement for the fetch step.

Everywhere else EventScout reads *raw* HTML (httpx). That misses events that only exist after a
SPA's JavaScript runs (React/Angular/Vue/Next/Nuxt hydration, infinite scroll, lazy loading, XHR /
GraphQL runtime APIs). This module drives a real headless Chrome (Playwright, reusing the system
Chrome — no bundled download) to produce the *final rendered DOM* plus the *network JSON/GraphQL
payloads* the page fetched at runtime. It is only the fetch step: extraction stays in the Universal
Event Engine. Respects robots.txt, rate-limits per domain, and caches rendered results.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.cache import TTLCache

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
# response bodies larger than this are skipped (not event listings)
_MAX_JSON_BYTES = 3_000_000


@dataclass
class RenderedPage:
    """The output of the browser fetch: the final DOM + captured runtime JSON/GraphQL bodies."""

    url: str
    dom: str = ""
    json_payloads: list[tuple[str, str]] = field(default_factory=list)  # (response_url, body)
    ok: bool = False
    reason: str = ""


class BrowserRenderer:
    def __init__(
        self,
        *,
        user_agent: str = _UA,
        rate_limit_seconds: float = 2.0,
        ttl_seconds: float = 3600,
        wait_ms: int = 3000,
        nav_timeout_ms: int = 40_000,
        respect_robots: bool = True,
        channel: str = "chrome",
    ) -> None:
        self._ua = user_agent
        self._rate = rate_limit_seconds
        self._cache: TTLCache[str, RenderedPage] = TTLCache(ttl_seconds)
        self._wait_ms = wait_ms
        self._nav_timeout = nav_timeout_ms
        self._respect_robots = respect_robots
        self._channel = channel
        self._pw = None
        self._browser = None
        self._launch_lock = asyncio.Lock()
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._rendered_count = 0

    # -- lifecycle ----------------------------------------------------------

    async def _ensure_browser(self) -> None:
        async with self._launch_lock:
            if self._browser is None:
                from playwright.async_api import async_playwright

                self._pw = await async_playwright().start()
                self._browser = await self._pw.chromium.launch(
                    channel=self._channel, headless=True, args=["--no-sandbox"]
                )
                logger.info("browser renderer: launched headless %s", self._channel)

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None

    @property
    def rendered_count(self) -> int:
        return self._rendered_count

    # -- robots + rate limiting --------------------------------------------

    async def _allowed(self, url: str) -> bool:
        if not self._respect_robots:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            self._robots[origin] = await self._load_robots(origin)
        rp = self._robots[origin]
        return True if rp is None else rp.can_fetch(self._ua, url)

    async def _load_robots(self, origin: str) -> RobotFileParser | None:
        rp = RobotFileParser()
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(f"{origin}/robots.txt", headers={"User-Agent": self._ua})
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
                return rp
        except httpx.HTTPError:
            pass
        return None  # no robots.txt reachable -> allow (fail-open, but polite via rate limit)

    async def _rate_limit(self, domain: str) -> None:
        last = self._last_hit.get(domain)
        if last is not None:
            wait = self._rate - (time.monotonic() - last)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_hit[domain] = time.monotonic()

    # -- render -------------------------------------------------------------

    async def render(self, url: str) -> RenderedPage:
        cached = self._cache.get(url)
        if cached is not None:
            return cached
        if not await self._allowed(url):
            logger.info("browser renderer: robots.txt disallows %s", url)
            return RenderedPage(url=url, reason="robots_disallow")

        await self._ensure_browser()
        await self._rate_limit(urlsplit(url).netloc)

        page = await self._browser.new_page(user_agent=self._ua)
        payloads: list[tuple[str, str]] = []

        async def _on_response(resp) -> None:
            try:
                if "json" not in resp.headers.get("content-type", ""):
                    return
                body = await resp.body()
                if 0 < len(body) <= _MAX_JSON_BYTES:
                    payloads.append((resp.url, body.decode("utf-8", "ignore")))
            except Exception:  # noqa: BLE001 — a single unreadable response must not abort the render
                pass

        page.on("response", _on_response)
        result = RenderedPage(url=url)
        try:
            # domcontentloaded (not networkidle, which hangs on SPAs with live connections), then a
            # fixed settle so hydration / lazy-loaded / XHR content lands; grab whatever rendered.
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self._nav_timeout)
            except Exception as exc:  # noqa: BLE001 — a slow nav still often leaves usable DOM
                result.reason = f"nav:{type(exc).__name__}"
            await page.wait_for_timeout(self._wait_ms)
            dom = await page.content()
            if dom and len(dom) > 800:
                result.dom = dom
                result.json_payloads = payloads
                result.ok = True
                self._rendered_count += 1
        except Exception as exc:  # noqa: BLE001 — render failures are per-page, not fatal
            result.reason = type(exc).__name__
            logger.warning("browser renderer: render failed for %s: %s", url, result.reason)
        finally:
            await page.close()

        if result.ok:
            self._cache.set(url, result)
        return result
