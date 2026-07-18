"""Frontier Manager (Phase 6F / D3).

Tracks what the discovery process has already seen so identical pages are never rediscovered:

- `known_urls`     — URLs already in the Discovery Inbox (seeded from prior runs → cross-run dedup)
- `known_domains`  — registrable domains already represented in the inbox
- `seen_urls`      — URLs encountered during THIS run (within-run dedup)
- `pending`        — URLs accepted as new, queued as a hand-off list for a later D1/D2 crawl

`is_new(url)` is the single gate: a URL already known or already seen this run is not new. The
frontier holds identity only (strings) — it never fetches anything.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.discovery.urls import normalize_url, registrable_domain


class Frontier:
    def __init__(self, known_urls: Iterable[str] = (), known_domains: Iterable[str] = ()) -> None:
        self.known_urls: set[str] = {u for u in (normalize_url(x) for x in known_urls) if u}
        self.known_domains: set[str] = set(known_domains) | {
            registrable_domain(u) for u in self.known_urls
        }
        self.seen_urls: set[str] = set()
        self.pending: list[str] = []

    def is_new(self, url: str) -> bool:
        """True iff this exact page has neither been seen this run nor is already known."""
        return url not in self.seen_urls and url not in self.known_urls

    def record(self, url: str) -> None:
        """Mark a URL as seen this run (and remember its domain)."""
        self.seen_urls.add(url)
        self.known_domains.add(registrable_domain(url))

    def offer(self, url: str) -> bool:
        """Offer a URL to the frontier. Returns True if it was newly accepted (and queued)."""
        if not self.is_new(url):
            return False
        self.record(url)
        self.pending.append(url)
        return True

    def next_pending(self) -> str | None:
        return self.pending.pop(0) if self.pending else None

    def stats(self) -> dict[str, int]:
        return {
            "known_urls": len(self.known_urls),
            "known_domains": len(self.known_domains),
            "seen_urls": len(self.seen_urls),
            "pending": len(self.pending),
        }
