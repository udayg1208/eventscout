"""Frontier Manager (Phase 8C) — pending / visited / failed / blocked / deferred.

A priority queue of URLs to crawl, ordered by `ExpansionPriority` (highest first, deterministic
tiebreak by URL). A URL is offered once — re-offers (and URLs already known from the Discovery
Inbox) are refused, so the frontier never re-queues the same page.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class FrontierItem:
    priority: float
    url: str
    depth: int
    from_domain: str


class ExpansionFrontier:
    def __init__(self, known_urls: Iterable[str] = ()) -> None:
        self.pending: list[FrontierItem] = []
        self.visited: set[str] = set()
        self.failed: set[str] = set()
        self.blocked: set[str] = set()
        self.deferred: set[str] = set()
        self._seen: set[str] = set(known_urls)

    def offer(self, url: str, *, depth: int, from_domain: str, priority: float) -> bool:
        if url in self._seen:
            return False
        self._seen.add(url)
        self.pending.append(FrontierItem(priority, url, depth, from_domain))
        # highest priority first; stable, deterministic tiebreak by URL
        self.pending.sort(key=lambda i: (-i.priority, i.url))
        return True

    def next_item(self) -> FrontierItem | None:
        return self.pending.pop(0) if self.pending else None

    def mark_visited(self, url: str) -> None:
        self.visited.add(url)

    def mark_failed(self, url: str) -> None:
        self.failed.add(url)

    def mark_blocked(self, url: str) -> None:
        self.blocked.add(url)

    def mark_deferred(self, url: str) -> None:
        self.deferred.add(url)

    def stats(self) -> dict:
        return {
            "pending": len(self.pending),
            "visited": len(self.visited),
            "failed": len(self.failed),
            "blocked": len(self.blocked),
            "deferred": len(self.deferred),
            "seen": len(self._seen),
        }
