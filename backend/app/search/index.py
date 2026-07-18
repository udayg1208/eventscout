"""Search Index — a keyword-searchable projection of the catalog.

The Repository stays the source of truth; the index is a rebuildable projection optimized
for full-text retrieval (bm25 relevance, tokenization). `SearchIndex` is the abstraction;
`SQLiteFTS5Index` is the first implementation. Postgres FTS / Meilisearch / Typesense
implement the same interface later with no change to retrievers (see SEARCH_INFRASTRUCTURE.md).

The Repository is not modified — this is a separate index, populated from the catalog.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

_SCHEMA = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5("
    "key UNINDEXED, title, description, city, organizer, tags, "
    "tokenize='porter unicode61')"
)


@dataclass(frozen=True)
class IndexDocument:
    """The indexed projection of one event. `organizer`/`tags` are future-safe columns —
    the schema carries them now; they populate when the data exists (Phase 5)."""

    key: str
    title: str
    description: str = ""
    city: str = ""
    organizer: str = ""  # future-safe (empty today)
    tags: str = ""  # future-safe (empty today)


class SearchIndex(ABC):
    @abstractmethod
    async def index(self, documents: Sequence[IndexDocument]) -> None:
        """Upsert documents (delete-then-insert by key)."""

    @abstractmethod
    async def rebuild(self, documents: Sequence[IndexDocument]) -> None:
        """Replace the entire index with `documents`."""

    @abstractmethod
    async def search(self, text: str, *, limit: int) -> list[tuple[str, float]]:
        """Return (event_key, score) best-first for the keyword `text`. Higher = better."""

    @abstractmethod
    async def delete(self, keys: Sequence[str]) -> None: ...

    @abstractmethod
    async def count(self) -> int: ...

    @abstractmethod
    async def close(self) -> None: ...


def _to_match(text: str) -> str:
    """Build a safe FTS5 MATCH expression: each term as a quoted phrase, OR-ed for recall
    (bm25 then floats the best matches to the top). Returns '' when there is nothing to match."""
    terms = [t for t in text.split() if t]
    quoted = [f'"{t.replace(chr(34), chr(34) * 2)}"' for t in terms]
    return " OR ".join(quoted)


class SQLiteFTS5Index(SearchIndex):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    async def index(self, documents: Sequence[IndexDocument]) -> None:
        await asyncio.to_thread(self._index_sync, documents)

    async def rebuild(self, documents: Sequence[IndexDocument]) -> None:
        await asyncio.to_thread(self._rebuild_sync, documents)

    async def search(self, text: str, *, limit: int) -> list[tuple[str, float]]:
        return await asyncio.to_thread(self._search_sync, text, limit)

    async def delete(self, keys: Sequence[str]) -> None:
        await asyncio.to_thread(self._delete_sync, keys)

    async def count(self) -> int:
        return await asyncio.to_thread(self._count_sync)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)

    # --- sync work (serialized) ---

    def _rows(self, documents: Sequence[IndexDocument]) -> list[tuple]:
        return [(d.key, d.title, d.description, d.city, d.organizer, d.tags) for d in documents]

    def _index_sync(self, documents: Sequence[IndexDocument]) -> None:
        with self._lock:
            for doc in documents:
                self._conn.execute("DELETE FROM events_fts WHERE key = ?", (doc.key,))
            self._conn.executemany(
                "INSERT INTO events_fts(key,title,description,city,organizer,tags) "
                "VALUES (?,?,?,?,?,?)",
                self._rows(documents),
            )
            self._conn.commit()

    def _rebuild_sync(self, documents: Sequence[IndexDocument]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM events_fts")
            self._conn.executemany(
                "INSERT INTO events_fts(key,title,description,city,organizer,tags) "
                "VALUES (?,?,?,?,?,?)",
                self._rows(documents),
            )
            self._conn.commit()

    def _search_sync(self, text: str, limit: int) -> list[tuple[str, float]]:
        match = _to_match(text)
        if not match:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, bm25(events_fts) AS score FROM events_fts "
                "WHERE events_fts MATCH ? ORDER BY score LIMIT ?",
                (match, limit),
            ).fetchall()
        # bm25 is smaller-is-better; negate so higher = more relevant.
        return [(key, -score) for key, score in rows]

    def _delete_sync(self, keys: Sequence[str]) -> None:
        with self._lock:
            self._conn.executemany("DELETE FROM events_fts WHERE key = ?", [(k,) for k in keys])
            self._conn.commit()

    def _count_sync(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM events_fts").fetchone()[0]
