"""Polite HTTP for web discovery (Phase 8B) — retries, backoff, robots, one UA.

`PoliteFetcher` wraps httpx with a discovery user-agent, a timeout, and exponential backoff on
429/5xx — so a flaky endpoint is retried gently, never hammered. `RobotsGate` reuses the D1 robots
parser to check whether a host permits a path before it is fetched (used for the DuckDuckGo HTML
endpoint; the JSON APIs are authorized calls). No browser, no Playwright — plain HTTP.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.discovery.robots import RobotsCache, parse_robots
from app.discovery.web.interfaces import ProviderError

DISCOVERY_WEB_UA = "EventScoutDiscoveryBot/1.0 (+https://eventscout.example/bot)"
_ROBOTS_UA_TOKEN = "eventscoutdiscoverybot"


@dataclass
class FetchResponse:
    status: int
    text: str
    url: str

    def json(self):
        import json

        return json.loads(self.text)


class PoliteFetcher:
    """httpx GET with UA + timeout + exponential backoff on 429/5xx; raises ProviderError."""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        client=None,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._client = client  # inject a fake in tests; real httpx client created lazily

    async def _do_get(self, url: str, params: dict | None, headers: dict | None) -> FetchResponse:
        merged = {"User-Agent": DISCOVERY_WEB_UA, **(headers or {})}
        if self._client is not None:  # injected (tests)
            resp = await self._client.get(url, params=params, headers=merged)
            return FetchResponse(status=resp.status_code, text=resp.text, url=str(resp.url))
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=merged)
            return FetchResponse(status=resp.status_code, text=resp.text, url=str(resp.url))

    async def get(
        self, url: str, *, params: dict | None = None, headers: dict | None = None
    ) -> FetchResponse:
        last_error = "unknown"
        for attempt in range(self._max_retries):
            try:
                resp = await self._do_get(url, params, headers)
            except Exception as exc:  # network error → backoff + retry
                last_error = f"network error: {exc}"
            else:
                if resp.status < 400:
                    return resp
                if resp.status in (429,) or resp.status >= 500:
                    last_error = f"HTTP {resp.status}"
                else:
                    raise ProviderError(f"HTTP {resp.status} for {url}")
            if attempt < self._max_retries - 1:
                await self._sleep(self._backoff_base * (2**attempt))
        raise ProviderError(f"giving up on {url} after {self._max_retries} attempts: {last_error}")


class RobotsGate:
    """robots.txt gate for hosts we scrape (reuses D1's RobotsCache). APIs don't need this."""

    def __init__(self, fetcher: PoliteFetcher) -> None:
        self._fetcher = fetcher
        self._cache: dict[str, object] = {}

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        policy = self._cache.get(origin)
        if policy is None:
            try:
                resp = await self._fetcher.get(origin + "/robots.txt")
                text = resp.text if resp.status < 400 else ""
            except ProviderError:
                text = ""  # fetch failed → assume allowed, stay polite via rate limits
            policy = parse_robots(text, _ROBOTS_UA_TOKEN)
            self._cache[origin] = policy
        return policy.allowed(parts.path or "/")


# a module-level RobotsCache type reference so callers can reuse the D1 machinery directly too
__all__ = ["DISCOVERY_WEB_UA", "PoliteFetcher", "FetchResponse", "RobotsGate", "RobotsCache"]
