"""HTTP fetch abstraction for the Discovery Engine.

Injectable so tests run with zero network (`StaticFetcher`). Production uses httpx — **no
JavaScript browser, no Playwright/Selenium** (per D1 rules): structured discovery reads the
raw HTML/feed bytes only. Identifiable, polite user-agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx

DISCOVERY_UA = "EventScoutDiscoveryBot/1.0 (+https://eventscout.example/bot)"
_MAX_BYTES = 3_000_000


@dataclass(frozen=True)
class FetchResult:
    url: str  # final URL after redirects
    status: int
    content_type: str  # bare type, lowercased (no charset)
    text: str
    headers: dict[str, str] = field(default_factory=dict)


class Fetcher(Protocol):
    async def get(self, url: str) -> FetchResult | None: ...


class HttpxFetcher:
    """Production fetcher. Returns None on any network/transport error (never raises)."""

    def __init__(
        self, *, timeout: float = 15.0, user_agent: str = DISCOVERY_UA, max_bytes: int = _MAX_BYTES
    ) -> None:
        self._timeout = timeout
        self._ua = user_agent
        self._max_bytes = max_bytes

    async def get(self, url: str) -> FetchResult | None:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": self._ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml,"
                    "text/calendar,application/json;q=0.9,*/*;q=0.8",
                },
            ) as client:
                response = await client.get(url)
        except httpx.HTTPError:
            return None
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        text = response.text
        if len(text) > self._max_bytes:
            text = text[: self._max_bytes]
        return FetchResult(
            url=str(response.url),
            status=response.status_code,
            content_type=content_type,
            text=text,
            headers={k.lower(): v for k, v in response.headers.items()},
        )


class StaticFetcher:
    """Test fetcher: serves canned responses keyed by the requested URL. Records calls."""

    def __init__(self, responses: dict[str, FetchResult]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    async def get(self, url: str) -> FetchResult | None:
        self.calls.append(url)
        return self._responses.get(url)
