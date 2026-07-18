"""Result normalization (Phase 8B) — canonical URLs, domains, dedup.

Turns raw `SearchResult`s into D3 `ParsedResult`s (reusing D3's `parse_results` for URL
canonicalization + registrable domain), strips tracking parameters, and de-duplicates across
queries by normalized URL. Producing `ParsedResult` means the rest of the pipeline — D3 ranking and
candidate building — is reused unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.discovery.search import SearchResult, parse_results
from app.discovery.search.parser import ParsedResult

# common tracking params to drop before dedup (utm_*, gclid, fbclid, ref, …)
_TRACKING = re.compile(r"(?i)(^utm_|^gclid$|^fbclid$|^ref$|^ref_src$|^mc_cid$|^mc_eid$|^igshid$)")


def _strip_tracking(url: str) -> str:
    if "?" not in url:
        return url
    base, query = url.split("?", 1)
    kept = [
        pair for pair in query.split("&") if pair and not _TRACKING.match(pair.split("=", 1)[0])
    ]
    return f"{base}?{'&'.join(kept)}" if kept else base


def normalize_results(results: Iterable[SearchResult], query: str) -> list[ParsedResult]:
    """Normalize one query's results into deduped ParsedResults (reuses D3's parser)."""
    cleaned = [
        SearchResult(
            title=r.title,
            url=_strip_tracking(r.url),
            snippet=r.snippet,
            rank=r.rank,
            engine=r.engine,
        )
        for r in results
    ]
    return parse_results(cleaned, query)


def dedupe_across(results: Iterable[ParsedResult]) -> list[ParsedResult]:
    """Collapse identical normalized URLs surfaced by different queries (keep best rank)."""
    best: dict[str, ParsedResult] = {}
    order: list[str] = []
    for r in results:
        cur = best.get(r.url)
        if cur is None:
            best[r.url] = r
            order.append(r.url)
        elif r.rank and (not cur.rank or r.rank < cur.rank):
            best[r.url] = r
    return [best[u] for u in order]
