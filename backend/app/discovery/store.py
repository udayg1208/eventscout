"""Discovery Inbox + crawl-checkpoint persistence.

Storage-agnostic contracts (mirroring the Repository pattern), with in-memory
implementations for tests and SQLite implementations for persistence. The inbox dedups by
candidate `key` (normalized URL / domain-scoped), so re-discovery updates rather than
duplicates. Nothing here advances a candidate past NEW automatically — approve/reject are
manual (`set_status`) for later phases.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import UTC, datetime

from app.discovery.models import (
    CandidateSource,
    ConfidenceSignals,
    CrawlRecord,
    DiscoveryStatus,
    FeedType,
)

# ------------------------------ Discovery Inbox ------------------------------


class DiscoveryInbox(ABC):
    @abstractmethod
    async def upsert(self, candidate: CandidateSource) -> str:
        """Insert or update by key; returns 'inserted' | 'updated'."""

    @abstractmethod
    async def get(self, key: str) -> CandidateSource | None: ...

    @abstractmethod
    async def list(
        self, *, status: DiscoveryStatus | None = None, limit: int = 100, offset: int = 0
    ) -> list[CandidateSource]: ...

    @abstractmethod
    async def set_status(self, key: str, status: DiscoveryStatus, reason: str = "") -> bool: ...

    @abstractmethod
    async def count(self, *, status: DiscoveryStatus | None = None) -> int: ...

    async def close(self) -> None:  # optional
        return None


def _merge_on_update(new: CandidateSource, existing: CandidateSource) -> CandidateSource:
    """Preserve first_seen + a manually-advanced status; bump version; refresh last_seen."""
    return replace(
        new,
        first_seen_at=existing.first_seen_at,
        version=existing.version + 1,
        status=existing.status if existing.status != DiscoveryStatus.NEW else new.status,
        status_reason=existing.status_reason
        if existing.status != DiscoveryStatus.NEW
        else new.status_reason,
    )


class InMemoryDiscoveryInbox(DiscoveryInbox):
    def __init__(self) -> None:
        self._rows: dict[str, CandidateSource] = {}

    async def upsert(self, candidate: CandidateSource) -> str:
        existing = self._rows.get(candidate.key)
        if existing is None:
            self._rows[candidate.key] = candidate
            return "inserted"
        self._rows[candidate.key] = _merge_on_update(candidate, existing)
        return "updated"

    async def get(self, key: str) -> CandidateSource | None:
        return self._rows.get(key)

    async def list(self, *, status=None, limit=100, offset=0) -> list[CandidateSource]:
        items = [c for c in self._rows.values() if status is None or c.status == status]
        items.sort(key=lambda c: c.key)
        return items[offset : offset + limit]

    async def set_status(self, key: str, status: DiscoveryStatus, reason: str = "") -> bool:
        row = self._rows.get(key)
        if row is None:
            return False
        row.status = status
        row.status_reason = reason
        row.version += 1
        return True

    async def count(self, *, status=None) -> int:
        return sum(1 for c in self._rows.values() if status is None or c.status == status)


# ------------------------------ Crawl checkpoints ------------------------------


class CrawlCheckpointStore(ABC):
    @abstractmethod
    async def record(self, url: str, domain: str, crawled_at: datetime, status: int) -> None: ...

    @abstractmethod
    async def was_crawled_since(self, url: str, since: datetime) -> bool: ...

    @abstractmethod
    async def visited_count(self, *, domain: str | None = None) -> int: ...

    async def close(self) -> None:
        return None


class InMemoryCrawlCheckpointStore(CrawlCheckpointStore):
    def __init__(self) -> None:
        self._rows: dict[str, CrawlRecord] = {}

    async def record(self, url: str, domain: str, crawled_at: datetime, status: int) -> None:
        self._rows[url] = CrawlRecord(url, domain, crawled_at, status)

    async def was_crawled_since(self, url: str, since: datetime) -> bool:
        row = self._rows.get(url)
        return row is not None and row.crawled_at >= since

    async def visited_count(self, *, domain: str | None = None) -> int:
        return sum(1 for r in self._rows.values() if domain is None or r.domain == domain)


# ------------------------------ SQLite persistence ------------------------------


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SQLiteDiscoveryInbox(DiscoveryInbox):
    """Persistent inbox. Sync sqlite work off the event loop via to_thread + a lock."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS candidates (
                key TEXT PRIMARY KEY, url TEXT, domain TEXT, feed_type TEXT, title TEXT,
                organization TEXT, country TEXT, city TEXT,
                technology_confidence REAL, india_confidence REAL, professional_confidence REAL,
                structured_data_score INTEGER, signals TEXT, discovery_method TEXT,
                discovery_path TEXT, status TEXT, status_reason TEXT,
                crawl_timestamp TEXT, first_seen_at TEXT, last_seen_at TEXT, version INTEGER,
                framework_data TEXT, search_data TEXT, ai_data TEXT
            )"""
        )
        # Additive, non-breaking migrations: append any JSON extension column that predates this
        # build (framework_data → D2, search_data → D3, ai_data → D4). Existing rows get NULL.
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(candidates)")}
        for column in ("framework_data", "search_data", "ai_data"):
            if column not in cols:
                self._conn.execute(f"ALTER TABLE candidates ADD COLUMN {column} TEXT")
        self._conn.commit()

    def _row_to_candidate(self, r: tuple) -> CandidateSource:
        fw = json.loads(r[21]) if len(r) > 21 and r[21] else {}
        sd = json.loads(r[22]) if len(r) > 22 and r[22] else {}
        ai = json.loads(r[23]) if len(r) > 23 and r[23] else {}
        return CandidateSource(
            key=r[0],
            url=r[1],
            domain=r[2],
            feed_type=FeedType(r[3]),
            title=r[4],
            organization=r[5],
            country=r[6],
            city=r[7],
            technology_confidence=r[8],
            india_confidence=r[9],
            professional_confidence=r[10],
            structured_data_score=r[11],
            signals=ConfidenceSignals(**json.loads(r[12])),
            discovery_method=r[13],
            discovery_path=json.loads(r[14]),
            status=DiscoveryStatus(r[15]),
            status_reason=r[16],
            crawl_timestamp=_parse_dt(r[17]),
            first_seen_at=_parse_dt(r[18]),
            last_seen_at=_parse_dt(r[19]),
            version=r[20],
            framework=fw.get("framework"),
            framework_version=fw.get("framework_version"),
            api_endpoints=fw.get("api_endpoints", []),
            graphql_endpoints=fw.get("graphql_endpoints", []),
            hydration_source=fw.get("hydration_source"),
            embedded_event_count=fw.get("embedded_event_count", 0),
            discovered_by=sd.get("discovered_by", "crawl"),
            search_query=sd.get("search_query"),
            search_rank=sd.get("search_rank"),
            search_engine=sd.get("search_engine"),
            discovery_confidence=ai.get("discovery_confidence"),
            classification=ai.get("classification"),
        )

    def _write(self, c: CandidateSource) -> None:
        framework_data = json.dumps(
            {
                "framework": c.framework,
                "framework_version": c.framework_version,
                "api_endpoints": c.api_endpoints,
                "graphql_endpoints": c.graphql_endpoints,
                "hydration_source": c.hydration_source,
                "embedded_event_count": c.embedded_event_count,
            }
        )
        search_data = json.dumps(
            {
                "discovered_by": c.discovered_by,
                "search_query": c.search_query,
                "search_rank": c.search_rank,
                "search_engine": c.search_engine,
            }
        )
        ai_data = json.dumps(
            {"discovery_confidence": c.discovery_confidence, "classification": c.classification}
        )
        placeholders = ",".join("?" * 24)
        self._conn.execute(
            f"INSERT OR REPLACE INTO candidates VALUES ({placeholders})",
            (
                c.key,
                c.url,
                c.domain,
                c.feed_type.value,
                c.title,
                c.organization,
                c.country,
                c.city,
                c.technology_confidence,
                c.india_confidence,
                c.professional_confidence,
                c.structured_data_score,
                json.dumps(c.signals.as_dict()),
                c.discovery_method,
                json.dumps(c.discovery_path),
                c.status.value,
                c.status_reason,
                _dt(c.crawl_timestamp),
                _dt(c.first_seen_at),
                _dt(c.last_seen_at),
                c.version,
                framework_data,
                search_data,
                ai_data,
            ),
        )
        self._conn.commit()

    def _upsert_sync(self, candidate: CandidateSource) -> str:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM candidates WHERE key=?", (candidate.key,))
            row = cur.fetchone()
            if row is None:
                self._write(candidate)
                return "inserted"
            self._write(_merge_on_update(candidate, self._row_to_candidate(row)))
            return "updated"

    async def upsert(self, candidate: CandidateSource) -> str:
        return await asyncio.to_thread(self._upsert_sync, candidate)

    async def get(self, key: str) -> CandidateSource | None:
        def _get() -> CandidateSource | None:
            with self._lock:
                row = self._conn.execute("SELECT * FROM candidates WHERE key=?", (key,)).fetchone()
            return self._row_to_candidate(row) if row else None

        return await asyncio.to_thread(_get)

    async def list(self, *, status=None, limit=100, offset=0) -> list[CandidateSource]:
        def _list() -> list[CandidateSource]:
            with self._lock:
                if status is None:
                    rows = self._conn.execute(
                        "SELECT * FROM candidates ORDER BY key LIMIT ? OFFSET ?", (limit, offset)
                    ).fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT * FROM candidates WHERE status=? ORDER BY key LIMIT ? OFFSET ?",
                        (status.value, limit, offset),
                    ).fetchall()
            return [self._row_to_candidate(r) for r in rows]

        return await asyncio.to_thread(_list)

    async def set_status(self, key: str, status: DiscoveryStatus, reason: str = "") -> bool:
        def _set() -> bool:
            with self._lock:
                cur = self._conn.execute(
                    "UPDATE candidates SET status=?, status_reason=?, version=version+1 "
                    "WHERE key=?",
                    (status.value, reason, key),
                )
                self._conn.commit()
                return cur.rowcount > 0

        return await asyncio.to_thread(_set)

    async def count(self, *, status=None) -> int:
        def _count() -> int:
            with self._lock:
                if status is None:
                    return self._conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
                return self._conn.execute(
                    "SELECT COUNT(*) FROM candidates WHERE status=?", (status.value,)
                ).fetchone()[0]

        return await asyncio.to_thread(_count)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)


class SQLiteCrawlCheckpointStore(CrawlCheckpointStore):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS crawl_log "
            "(url TEXT PRIMARY KEY, domain TEXT, crawled_at TEXT, status INTEGER)"
        )
        self._conn.commit()

    async def record(self, url: str, domain: str, crawled_at: datetime, status: int) -> None:
        def _rec() -> None:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO crawl_log VALUES (?,?,?,?)",
                    (url, domain, crawled_at.isoformat(), status),
                )
                self._conn.commit()

        await asyncio.to_thread(_rec)

    async def was_crawled_since(self, url: str, since: datetime) -> bool:
        def _q() -> bool:
            with self._lock:
                row = self._conn.execute(
                    "SELECT crawled_at FROM crawl_log WHERE url=?", (url,)
                ).fetchone()
            return row is not None and datetime.fromisoformat(row[0]) >= since

        return await asyncio.to_thread(_q)

    async def visited_count(self, *, domain: str | None = None) -> int:
        def _c() -> int:
            with self._lock:
                if domain is None:
                    return self._conn.execute("SELECT COUNT(*) FROM crawl_log").fetchone()[0]
                return self._conn.execute(
                    "SELECT COUNT(*) FROM crawl_log WHERE domain=?", (domain,)
                ).fetchone()[0]

        return await asyncio.to_thread(_c)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)


def utcnow() -> datetime:
    return datetime.now(UTC)
