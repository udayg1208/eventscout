"""Web Expansion domain models (Phase 8C).

The expansion layer grows a persistent **Discovery Graph** from every page it crawls — nodes for
pages/domains/feeds/calendars/communities/GitHub/Notion/Discord/Telegram/… and typed edges between
them. It reuses D1's fetcher/robots/link/feed machinery, adds recursion under strict scope + budget,
and ends at the Discovery Inbox. Nothing here is onboarded or promoted; everything is additive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class NodeType(StrEnum):
    PAGE = "page"
    DOMAIN = "domain"
    RSS = "rss"
    ICS = "ics"
    JSONLD = "jsonld"
    SITEMAP = "sitemap"
    BLOG = "blog"
    COMMUNITY = "community"
    ORGANIZER = "organizer"
    CALENDAR = "calendar"
    GITHUB = "github"
    NOTION = "notion"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    UNIVERSITY = "university"
    COMPANY = "company"


class EdgeType(StrEnum):
    LINKS_TO = "links_to"
    OWNS = "owns"
    HOSTS = "hosts"
    REFERENCES = "references"
    BELONGS_TO = "belongs_to"
    CONTAINS_CALENDAR = "contains_calendar"
    CONTAINS_FEED = "contains_feed"
    CONTAINS_EVENTS = "contains_events"


# Node types that are "leaf" discovered sources worth an inbox candidate (not navigational).
SOURCE_NODES = frozenset(
    {
        NodeType.RSS,
        NodeType.ICS,
        NodeType.JSONLD,
        NodeType.CALENDAR,
        NodeType.COMMUNITY,
        NodeType.ORGANIZER,
        NodeType.GITHUB,
        NodeType.NOTION,
        NodeType.DISCORD,
        NodeType.TELEGRAM,
        NodeType.BLOG,
    }
)


@dataclass
class GraphNode:
    key: str  # canonical identity (dedup key)
    node_type: NodeType
    url: str
    domain: str
    title: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    attrs: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "node_type": self.node_type.value,
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "attrs": self.attrs,
        }


@dataclass(frozen=True)
class GraphEdge:
    source: str  # node key
    target: str  # node key
    edge_type: EdgeType

    def as_dict(self) -> dict:
        return {"source": self.source, "target": self.target, "edge_type": self.edge_type.value}


@dataclass
class ExpansionPriority:
    score: float  # 0..1
    signals: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"score": self.score, "signals": self.signals, "reasons": self.reasons}


@dataclass(frozen=True)
class CrawlBudgetConfig:
    max_pages: int = 25  # per domain
    max_depth: int = 2
    max_failures: int = 3
    cooldown_seconds: float = 60.0
    daily_limit: int = 500
    max_bandwidth_bytes: int = 5_000_000  # ~5 MB/domain/run


# Frozen default so signatures don't call CrawlBudgetConfig() in their arg defaults (B008).
DEFAULT_CRAWL_BUDGET = CrawlBudgetConfig()


@dataclass
class CheckpointRecord:
    url: str
    domain: str
    depth: int = 0
    visited_at: datetime | None = None
    etag: str | None = None
    last_modified: str | None = None
    last_crawl: datetime | None = None
    failure_count: int = 0
    robots_version: str | None = None  # hash/marker of the robots.txt seen

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "domain": self.domain,
            "depth": self.depth,
            "visited_at": self.visited_at.isoformat() if self.visited_at else None,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "last_crawl": self.last_crawl.isoformat() if self.last_crawl else None,
            "failure_count": self.failure_count,
            "robots_version": self.robots_version,
        }


@dataclass
class ExpansionReport:
    seeds: int = 0
    pages_fetched: int = 0
    pages_skipped: int = 0
    nodes_added: int = 0
    edges_added: int = 0
    feeds_found: int = 0
    calendars_found: int = 0
    communities_found: int = 0
    github_found: int = 0
    notion_found: int = 0
    discord_found: int = 0
    telegram_found: int = 0
    blogs_found: int = 0
    candidates_inserted: int = 0
    candidates_updated: int = 0
    dedup_merged: int = 0
    frontier: dict = field(default_factory=dict)
    nodes_by_type: dict = field(default_factory=dict)
    edges_by_type: dict = field(default_factory=dict)
    stopped_domains: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()
