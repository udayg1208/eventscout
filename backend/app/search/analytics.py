"""Search analytics — platform-level (no user tracking).

Aggregate counters and popularity histograms recorded on every search that reaches the
read-path provider: volume, latency, result counts, cache hits, empty searches, and the
most-requested categories / cities / topics. In-memory today; a `snapshot()` renders it.
"""

from __future__ import annotations

from collections import Counter

from app.models.search import SearchQuery


class SearchAnalytics:
    def __init__(self) -> None:
        self.total_searches = 0
        self.empty_searches = 0
        self.cache_hits = 0
        self.total_latency_ms = 0.0
        self.total_results = 0
        self._categories: Counter[str] = Counter()
        self._cities: Counter[str] = Counter()
        self._topics: Counter[str] = Counter()  # keywords stand in for topics until Phase 5

    def record(
        self, query: SearchQuery, *, result_count: int, latency_ms: float, cache_hit: bool
    ) -> None:
        self.total_searches += 1
        self.total_latency_ms += latency_ms
        self.total_results += result_count
        if result_count == 0:
            self.empty_searches += 1
        if cache_hit:
            self.cache_hits += 1
        for category in query.categories:
            self._categories[category.value] += 1
        if query.city:
            self._cities[query.city.casefold()] += 1
        for keyword in query.keywords:
            self._topics[keyword.casefold()] += 1

    def snapshot(self) -> dict:
        n = self.total_searches
        return {
            "total_searches": n,
            "empty_searches": self.empty_searches,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": round(self.cache_hits / n, 4) if n else 0.0,
            "avg_latency_ms": round(self.total_latency_ms / n, 3) if n else 0.0,
            "avg_result_count": round(self.total_results / n, 2) if n else 0.0,
            "popular_categories": self._categories.most_common(5),
            "popular_cities": self._cities.most_common(5),
            "popular_topics": self._topics.most_common(5),
        }
