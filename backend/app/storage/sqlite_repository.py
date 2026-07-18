"""SQLite implementation of `EventRepository` (v2) — the first storage backend.

Stdlib ``sqlite3`` (zero extra dependencies). All SQL runs inside ``asyncio.to_thread``
so the async event loop is never blocked, and a ``threading.Lock`` serializes access to
the single connection (loop-agnostic — works from one event loop or across many). A later
Postgres backend implements the same interface; no application code changes.

Writes are **set-based** (batched SELECT → classify → `executemany`), reads are
**keyset-paginated** and **streamable**, and the record lifecycle is a status column — so
this backend behaves correctly whether the catalog holds hundreds or millions of rows.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import replace
from datetime import date, datetime

from app.models.event import Event, EventCategory
from app.storage.models import (
    EventStatus,
    Page,
    SearchCriteria,
    StoredEvent,
    UpsertResult,
    decode_cursor,
    encode_cursor,
)
from app.storage.repository import EventRepository

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    key           TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT,
    url           TEXT NOT NULL,
    city          TEXT,
    location      TEXT,
    is_online     INTEGER NOT NULL DEFAULT 0,
    start_date    TEXT NOT NULL,
    end_date      TEXT,
    category      TEXT NOT NULL,
    is_free       INTEGER,            -- 0 / 1 / NULL (NULL = source did not say)
    price         TEXT,
    provider      TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',
    status_reason TEXT,
    version       INTEGER NOT NULL DEFAULT 1
);
-- Serves the common filtered + keyset-ordered read: status gate, then (start_date, key).
CREATE INDEX IF NOT EXISTS idx_events_status_start_key ON events(status, start_date, key);
CREATE INDEX IF NOT EXISTS idx_events_start_key        ON events(start_date, key);
CREATE INDEX IF NOT EXISTS idx_events_city             ON events(city);
CREATE INDEX IF NOT EXISTS idx_events_category         ON events(category);
"""

_COLUMNS = (
    "key, title, description, url, city, location, is_online, start_date, end_date, "
    "category, is_free, price, provider, content_hash, first_seen_at, last_seen_at, "
    "status, status_reason, version"
)
_INSERT_SQL = (
    f"INSERT INTO events ({_COLUMNS}) VALUES ("
    ":key, :title, :description, :url, :city, :location, :is_online, :start_date, "
    ":end_date, :category, :is_free, :price, :provider, :content_hash, :first_seen_at, "
    ":last_seen_at, :status, :status_reason, :version)"
)
# Content changed: rewrite everything except key and first_seen_at (provenance preserved).
_UPDATE_SQL = (
    "UPDATE events SET title=:title, description=:description, url=:url, city=:city, "
    "location=:location, is_online=:is_online, start_date=:start_date, end_date=:end_date, "
    "category=:category, is_free=:is_free, price=:price, provider=:provider, "
    "content_hash=:content_hash, last_seen_at=:last_seen_at, status=:status, "
    "status_reason=:status_reason, version=:version WHERE key=:key"
)
# Content unchanged: only confirm freshness and (re)assert presence.
_TOUCH_SQL = (
    "UPDATE events SET last_seen_at=:last_seen_at, status=:status, "
    "status_reason=:status_reason WHERE key=:key"
)

_IN_CHUNK = 500  # keep IN(...) parameter lists well under SQLite's limit


def _chunks(seq: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


class SQLiteEventRepository(EventRepository):
    """SQLite-backed event store. Pass a file path for durability, or the default
    ``:memory:`` for tests."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")  # readers + a writer coexist
        self._lock = threading.Lock()
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- async interface (offloads sync sqlite to a worker thread) -----------------

    async def bulk_upsert(self, records: Sequence[StoredEvent]) -> UpsertResult:
        return await asyncio.to_thread(self._bulk_upsert_sync, records)

    async def bulk_set_status(
        self, keys: Sequence[str], status: EventStatus, *, reason: str | None = None
    ) -> int:
        return await asyncio.to_thread(self._bulk_set_status_sync, keys, status, reason)

    async def expire_ended(self, *, today: date) -> int:
        return await asyncio.to_thread(self._expire_ended_sync, today)

    async def archive_before(self, *, cutoff: date) -> int:
        return await asyncio.to_thread(self._archive_before_sync, cutoff)

    async def search(self, criteria: SearchCriteria) -> Page:
        return await asyncio.to_thread(self._search_sync, criteria)

    async def iterate(
        self, criteria: SearchCriteria, *, batch_size: int = 500
    ) -> AsyncIterator[StoredEvent]:
        cursor = criteria.cursor
        while True:
            page = await self.search(replace(criteria, cursor=cursor, limit=batch_size))
            for item in page.items:
                yield item
            if page.next_cursor is None:
                return
            cursor = page.next_cursor

    async def get(self, key: str) -> StoredEvent | None:
        return await asyncio.to_thread(self._get_sync, key)

    async def get_many(self, keys: Sequence[str]) -> dict[str, StoredEvent]:
        return await asyncio.to_thread(self._get_many_sync, keys)

    async def find_candidates(self, *, on_date: date, city: str | None = None) -> list[StoredEvent]:
        return await asyncio.to_thread(self._find_candidates_sync, on_date, city)

    async def count(self, criteria: SearchCriteria) -> int:
        return await asyncio.to_thread(self._count_sync, criteria)

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    # --- sync writes (serialized by the lock) --------------------------------------

    def _bulk_upsert_sync(self, records: Sequence[StoredEvent]) -> UpsertResult:
        # Collapse duplicate keys within the batch (keep the last occurrence).
        by_key: dict[str, StoredEvent] = {r.key: r for r in records}
        if not by_key:
            return UpsertResult()

        with self._lock:
            existing: dict[str, sqlite3.Row] = {}
            all_keys = list(by_key)
            for chunk in _chunks(all_keys, _IN_CHUNK):
                placeholders = ",".join("?" * len(chunk))
                rows = self._conn.execute(
                    f"SELECT key, content_hash, version, first_seen_at "
                    f"FROM events WHERE key IN ({placeholders})",
                    tuple(chunk),
                ).fetchall()
                for row in rows:
                    existing[row["key"]] = row

            inserts, updates, touches = [], [], []
            for record in by_key.values():
                prior = existing.get(record.key)
                if prior is None:
                    inserts.append(_row_params(record))
                elif prior["content_hash"] == record.content_hash:
                    touches.append(_touch_params(record))
                else:
                    updates.append(
                        _row_params(
                            record,
                            version=prior["version"] + 1,
                            first_seen_at=prior["first_seen_at"],
                        )
                    )

            if inserts:
                self._conn.executemany(_INSERT_SQL, inserts)
            if updates:
                self._conn.executemany(_UPDATE_SQL, updates)
            if touches:
                self._conn.executemany(_TOUCH_SQL, touches)
            self._conn.commit()

        return UpsertResult(inserted=len(inserts), updated=len(updates), unchanged=len(touches))

    def _bulk_set_status_sync(
        self, keys: Sequence[str], status: EventStatus, reason: str | None
    ) -> int:
        if not keys:
            return 0
        affected = 0
        with self._lock:
            for chunk in _chunks(list(keys), _IN_CHUNK):
                placeholders = ",".join("?" * len(chunk))
                cursor = self._conn.execute(
                    f"UPDATE events SET status=?, status_reason=? WHERE key IN ({placeholders})",
                    (status.value, reason, *chunk),
                )
                affected += cursor.rowcount
            self._conn.commit()
        return affected

    def _expire_ended_sync(self, today: date) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE events SET status='expired', status_reason='ended' "
                "WHERE status='active' AND COALESCE(end_date, start_date) < :today",
                {"today": today.isoformat()},
            )
            self._conn.commit()
            return cursor.rowcount

    def _archive_before_sync(self, cutoff: date) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE events SET status='archived', status_reason='archived' "
                "WHERE status='expired' AND COALESCE(end_date, start_date) < :cutoff",
                {"cutoff": cutoff.isoformat()},
            )
            self._conn.commit()
            return cursor.rowcount

    # --- sync reads ----------------------------------------------------------------

    def _search_sync(self, criteria: SearchCriteria) -> Page:
        where, params = _build_where(criteria)
        if criteria.cursor:
            cursor_date, cursor_key = decode_cursor(criteria.cursor)
            where.append(
                "(start_date > :cursor_date OR (start_date = :cursor_date AND key > :cursor_key))"
            )
            params["cursor_date"] = cursor_date.isoformat()
            params["cursor_key"] = cursor_key

        sql = "SELECT * FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY start_date, key"
        if criteria.limit is not None:
            sql += " LIMIT :limit"
            params["limit"] = criteria.limit + 1  # one extra row detects a next page

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        items = [_row_to_stored(row) for row in rows]

        next_cursor = None
        if criteria.limit is not None and len(items) > criteria.limit:
            items = items[: criteria.limit]
            last = items[-1]
            next_cursor = encode_cursor(last.event.start_date, last.key)
        return Page(items=items, next_cursor=next_cursor)

    def _get_sync(self, key: str) -> StoredEvent | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM events WHERE key = ?", (key,)).fetchone()
        return _row_to_stored(row) if row else None

    def _get_many_sync(self, keys: Sequence[str]) -> dict[str, StoredEvent]:
        if not keys:
            return {}
        found: dict[str, StoredEvent] = {}
        with self._lock:
            for chunk in _chunks(list(keys), _IN_CHUNK):
                placeholders = ",".join("?" * len(chunk))
                rows = self._conn.execute(
                    f"SELECT * FROM events WHERE key IN ({placeholders})", tuple(chunk)
                ).fetchall()
                for row in rows:
                    stored = _row_to_stored(row)
                    found[stored.key] = stored
        return found

    def _find_candidates_sync(self, on_date: date, city: str | None) -> list[StoredEvent]:
        sql = "SELECT * FROM events WHERE status='active' AND start_date = :d"
        params: dict[str, object] = {"d": on_date.isoformat()}
        if city:
            sql += " AND (city IS NULL OR lower(city) = lower(:city))"
            params["city"] = city
        sql += " ORDER BY key"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_stored(row) for row in rows]

    def _count_sync(self, criteria: SearchCriteria) -> int:
        where, params = _build_where(criteria)
        sql = "SELECT COUNT(*) AS n FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._lock:
            return self._conn.execute(sql, params).fetchone()["n"]

    def _close_sync(self) -> None:
        with self._lock:
            self._conn.close()


# --- row <-> model mapping (module-level pure helpers) -----------------------------


def _build_where(criteria: SearchCriteria) -> tuple[list[str], dict[str, object]]:
    """Translate filter criteria (no cursor/limit) into a WHERE fragment + params.
    Shared by search, iterate (via search) and count so their semantics never diverge."""
    where: list[str] = []
    params: dict[str, object] = {}

    if criteria.active_only:
        where.append("status = 'active'")
    if criteria.city:
        where.append("city IS NOT NULL AND lower(city) = lower(:city)")
        params["city"] = criteria.city
    if criteria.categories:
        names = [f":cat{i}" for i in range(len(criteria.categories))]
        where.append(f"category IN ({', '.join(names)})")
        for i, category in enumerate(criteria.categories):
            params[f"cat{i}"] = category.value
    if criteria.free_only:
        where.append("is_free = 1")
    if criteria.date_from:
        where.append("COALESCE(end_date, start_date) >= :date_from")
        params["date_from"] = criteria.date_from.isoformat()
    if criteria.date_to:
        where.append("start_date <= :date_to")
        params["date_to"] = criteria.date_to.isoformat()
    if criteria.upcoming_on_or_after:
        where.append("COALESCE(end_date, start_date) >= :upcoming")
        params["upcoming"] = criteria.upcoming_on_or_after.isoformat()
    if criteria.keywords:
        clauses = []
        for i, keyword in enumerate(criteria.keywords):
            clauses.append(
                f"(lower(title) LIKE :kw{i} OR lower(COALESCE(description, '')) LIKE :kw{i})"
            )
            params[f"kw{i}"] = f"%{keyword.casefold()}%"
        where.append("(" + " OR ".join(clauses) + ")")
    return where, params


def _row_params(
    record: StoredEvent, *, version: int | None = None, first_seen_at: str | None = None
) -> dict[str, object]:
    """Full column set for INSERT / content-changed UPDATE. `version` and `first_seen_at`
    override the record's own values on an update (bump version, preserve first_seen)."""
    e = record.event
    return {
        "key": record.key,
        "title": e.title,
        "description": e.description,
        "url": str(e.url),
        "city": e.city,
        "location": e.location,
        "is_online": 1 if e.is_online else 0,
        "start_date": e.start_date.isoformat(),
        "end_date": e.end_date.isoformat() if e.end_date else None,
        "category": e.category.value,
        "is_free": None if e.is_free is None else (1 if e.is_free else 0),
        "price": e.price,
        "provider": e.provider,
        "content_hash": record.content_hash,
        "first_seen_at": first_seen_at or record.first_seen_at.isoformat(),
        "last_seen_at": record.last_seen_at.isoformat(),
        "status": record.status.value,
        "status_reason": record.status_reason,
        "version": version if version is not None else record.version,
    }


def _touch_params(record: StoredEvent) -> dict[str, object]:
    return {
        "key": record.key,
        "last_seen_at": record.last_seen_at.isoformat(),
        "status": record.status.value,
        "status_reason": record.status_reason,
    }


def _row_to_stored(row: sqlite3.Row) -> StoredEvent:
    event = Event(
        title=row["title"],
        description=row["description"],
        url=row["url"],
        city=row["city"],
        location=row["location"],
        is_online=bool(row["is_online"]),
        start_date=date.fromisoformat(row["start_date"]),
        end_date=date.fromisoformat(row["end_date"]) if row["end_date"] else None,
        category=EventCategory(row["category"]),
        is_free=None if row["is_free"] is None else bool(row["is_free"]),
        price=row["price"],
        provider=row["provider"],
    )
    return StoredEvent(
        event=event,
        key=row["key"],
        content_hash=row["content_hash"],
        first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
        last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
        status=EventStatus(row["status"]),
        status_reason=row["status_reason"],
        version=row["version"],
    )
