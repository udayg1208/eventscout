"""DuckDuckGo provider (Phase 8B) — the zero-key real provider.

Two modes, both plain HTTP (no browser, no key):
- `html`  → GET https://html.duckduckgo.com/html/?q=… and parse the result anchors (real web SERP).
- `ia`    → GET https://api.duckduckgo.com/?q=…&format=json (official Instant Answer API; sparser,
            but stable/official — good when the HTML endpoint rate-limits or challenges).

DuckDuckGo wraps result links in a redirector (`/l/?uddg=<encoded>`); we decode back to the real
target. Respects the HTML host's robots via an optional `RobotsGate`. All DDG-specific logic here.
"""

from __future__ import annotations

import html as _html
import re
from urllib.parse import parse_qs, unquote, urlsplit

from app.discovery.web.fetch import PoliteFetcher, RobotsGate
from app.discovery.web.interfaces import (
    ProviderError,
    SearchProviderConfig,
    SearchResult,
    WebSearchProvider,
)

_RESULT_A = re.compile(
    r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)
_SNIPPET = re.compile(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    return _html.unescape(_TAGS.sub("", fragment)).strip()


def _decode_target(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parts = urlsplit(href)
    if "duckduckgo.com" in parts.netloc and parts.path.startswith("/l/"):
        uddg = parse_qs(parts.query).get("uddg", [None])[0]
        if uddg:
            return unquote(uddg)
    return href


def parse_ddg_html(html_text: str, limit: int) -> list[SearchResult]:
    anchors = _RESULT_A.findall(html_text)
    snippets = [_text(s) for s in _SNIPPET.findall(html_text)]
    out: list[SearchResult] = []
    for i, (href, title) in enumerate(anchors[:limit], start=1):
        url = _decode_target(href)
        if not url.startswith("http"):
            continue
        snippet = snippets[i - 1] if i - 1 < len(snippets) else ""
        out.append(
            SearchResult(title=_text(title), url=url, snippet=snippet, rank=i, engine="duckduckgo")
        )
    return out


class DuckDuckGoProvider(WebSearchProvider):
    name = "duckduckgo"
    HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
    IA_ENDPOINT = "https://api.duckduckgo.com/"

    def __init__(
        self,
        config: SearchProviderConfig | None = None,
        *,
        fetcher: PoliteFetcher,
        mode: str = "html",
        robots: RobotsGate | None = None,
    ) -> None:
        self._config = config or SearchProviderConfig()
        self._fetcher = fetcher
        self._mode = mode
        self._robots = robots

    @property
    def configured(self) -> bool:
        return True  # no key required

    async def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        if self._mode == "ia":
            return await self._instant_answer(query, limit)
        return await self._html_serp(query, limit)

    async def _html_serp(self, query: str, limit: int) -> list[SearchResult]:
        if self._robots is not None and not await self._robots.allowed(self.HTML_ENDPOINT):
            raise ProviderError("duckduckgo: robots.txt disallows the HTML endpoint")
        resp = await self._fetcher.get(self.HTML_ENDPOINT, params={"q": query, "kl": "in-en"})
        return parse_ddg_html(resp.text, limit)

    async def _instant_answer(self, query: str, limit: int) -> list[SearchResult]:
        resp = await self._fetcher.get(
            self.IA_ENDPOINT, params={"q": query, "format": "json", "no_html": 1, "no_redirect": 1}
        )
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError(f"duckduckgo: unparseable IA response ({exc})") from exc
        out: list[SearchResult] = []
        for i, topic in enumerate(data.get("RelatedTopics", []) or [], start=1):
            url = topic.get("FirstURL")
            if url:
                out.append(
                    SearchResult(
                        title=topic.get("Text", ""),
                        url=url,
                        snippet=topic.get("Text", ""),
                        rank=i,
                        engine="duckduckgo",
                    )
                )
            if len(out) >= limit:
                break
        return out
