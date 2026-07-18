"""Future organizer-intelligence seams (Phase 10C) — INTERFACES ONLY, no implementations.

10C builds the graph from served bytes it is handed, deterministically. These mark where later
phases plug in: a live social fetcher (pull a GitHub org / Discord landing page to enrich a channel
node — 8D public-only rules apply), and a graph-database backend for a large cross-source graph.
Each raises `NotImplementedError`; none run in 10C — no network, no browser, no login.
"""

from __future__ import annotations

from abc import abstractmethod


class SocialChannelFetcher:
    """FUTURE: fetch a public social/GitHub/Discord landing page to enrich a channel node.

    Public content only, robots-respected — the 8D social rules. Out of 10C's no-network scope."""

    @abstractmethod
    async def enrich(self, url: str) -> dict:  # pragma: no cover
        raise NotImplementedError("live social enrichment is deferred — 10C is byte-level only")


class GraphDatabaseBackend:
    """FUTURE: back the OrganizerGraph with a real graph DB for cross-source scale + queries."""

    @abstractmethod
    async def upsert(self, node_or_edge: dict) -> None:  # pragma: no cover
        raise NotImplementedError("graph-DB backend is deferred — 10C uses in-memory + SQLite")
