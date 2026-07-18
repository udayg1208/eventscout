"""Search Result Parser (Phase 6F / D3).

Turns raw `SearchResult` rows into normalized `ParsedResult`s: canonical URL (reusing D1's
`normalize_url`), registrable domain, trimmed title/snippet, plus the originating query/rank/engine
for provenance. Rows whose URL can't be normalized (mailto:, javascript:, fragments) are dropped,
and identical URLs within a single result set are collapsed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.discovery.search.search import SearchResult
from app.discovery.urls import normalize_url, registrable_domain


@dataclass(frozen=True)
class ParsedResult:
    title: str
    url: str  # normalized
    snippet: str
    domain: str  # registrable domain
    rank: int
    engine: str
    query: str


def parse_result(result: SearchResult, query: str) -> ParsedResult | None:
    """Normalize one row; return None if the URL is unusable."""
    norm = normalize_url(result.url)
    if not norm:
        return None
    return ParsedResult(
        title=(result.title or "").strip(),
        url=norm,
        snippet=(result.snippet or "").strip(),
        domain=registrable_domain(norm),
        rank=result.rank,
        engine=result.engine,
        query=query,
    )


def parse_results(results: Iterable[SearchResult], query: str) -> list[ParsedResult]:
    """Normalize a result set for one query, dropping junk and in-set duplicate URLs."""
    seen: set[str] = set()
    out: list[ParsedResult] = []
    for r in results:
        parsed = parse_result(r, query)
        if parsed is None or parsed.url in seen:
            continue
        seen.add(parsed.url)
        out.append(parsed)
    return out
