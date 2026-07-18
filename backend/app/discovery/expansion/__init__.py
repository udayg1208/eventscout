"""Autonomous Web Expansion (Phase 8C) — grow the Discovery Graph from every page.

Instead of stopping after a single discovered page, the expansion engine crawls it (HTML only, no
browser), extracts every kind of source (links, RSS/Atom, ICS/Google Calendar, JSON-LD, GitHub/
GitLab orgs, Notion, Discord, Telegram, blogs, communities), records them as a persistent
Discovery Graph, and recursively enqueues in-scope links under strict scope + budget + robots. Every
discovered source becomes a Discovery Inbox candidate (`discovered_by="expansion"`, `status=NEW`).

Strictly additive and discovery-only: no browser/Playwright/Selenium, no LLM, and no changes to
Search, the Repository, the Discovery Engine (D1–D4), Web Discovery (8B), providers, the scheduler,
Production, the Catalog, the frontend, or the API. Output stops at the Discovery Inbox.
"""

from app.discovery.expansion.budget import BudgetTracker
from app.discovery.expansion.checkpoint import (
    CheckpointStore,
    InMemoryCheckpointStore,
    SQLiteCheckpointStore,
)
from app.discovery.expansion.crawler import CrawlOutcome, ExpansionCrawler
from app.discovery.expansion.dedup import canonicalize, node_key
from app.discovery.expansion.engine import ExpansionEngine
from app.discovery.expansion.extractor import Extraction, extract
from app.discovery.expansion.frontier import ExpansionFrontier, FrontierItem
from app.discovery.expansion.graph import ExpansionGraph
from app.discovery.expansion.models import (
    CheckpointRecord,
    CrawlBudgetConfig,
    EdgeType,
    ExpansionPriority,
    ExpansionReport,
    GraphEdge,
    GraphNode,
    NodeType,
)
from app.discovery.expansion.priority import score_url
from app.discovery.expansion.scope import (
    ScopeConfig,
    ScopeDecision,
    evaluate_scope,
    is_crawlable,
)
from app.discovery.expansion.store import (
    ExpansionStore,
    InMemoryExpansionStore,
    SQLiteExpansionStore,
)

__all__ = [
    # models
    "NodeType",
    "EdgeType",
    "GraphNode",
    "GraphEdge",
    "ExpansionPriority",
    "CrawlBudgetConfig",
    "CheckpointRecord",
    "ExpansionReport",
    # graph
    "ExpansionGraph",
    # extraction
    "extract",
    "Extraction",
    # scope / priority / budget
    "ScopeConfig",
    "ScopeDecision",
    "evaluate_scope",
    "is_crawlable",
    "score_url",
    "BudgetTracker",
    # frontier / crawler
    "ExpansionFrontier",
    "FrontierItem",
    "ExpansionCrawler",
    "CrawlOutcome",
    # dedup / checkpoint / store
    "canonicalize",
    "node_key",
    "CheckpointStore",
    "InMemoryCheckpointStore",
    "SQLiteCheckpointStore",
    "ExpansionStore",
    "InMemoryExpansionStore",
    "SQLiteExpansionStore",
    # engine
    "ExpansionEngine",
]
