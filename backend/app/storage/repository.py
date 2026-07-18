"""The storage abstraction: `EventRepository` (v2).

Application code (search, ingestion) depends ONLY on this interface — never on a concrete
backend. SQLite is the first implementation; Postgres/Supabase will be a second
implementation of this same interface, added with **zero** application changes.

The surface is built for a catalog that scales to millions of records:
- **bulk** writes (set-based), not row-by-row;
- **keyset** pagination (`Page` + opaque cursor), never offset;
- **streaming** iteration that never materializes the full set in memory;
- a **status lifecycle** (expire / withdraw / archive) instead of a delete;
- bulk status/expiry/archive as set-based operations.

Async by design: the read path is async and a future asyncpg backend is natively async,
so both backends satisfy this contract without a signature change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from datetime import date

from app.storage.models import (
    EventStatus,
    Page,
    SearchCriteria,
    StoredEvent,
    UpsertResult,
)


class EventRepository(ABC):
    """Persistent store of events — the single source of truth."""

    # --- writes -------------------------------------------------------------

    @abstractmethod
    async def bulk_upsert(self, records: Sequence[StoredEvent]) -> UpsertResult:
        """Set-based upsert keyed by `StoredEvent.key`:

        - key absent            -> INSERT                       (inserted)
        - key present, same hash -> touch `last_seen_at`/status (unchanged)
        - key present, new hash  -> rewrite + bump `version`    (updated)

        `first_seen_at` is preserved across updates. Safe to call repeatedly with the
        same data (idempotent); duplicate keys within one batch collapse to the last.
        """

    @abstractmethod
    async def bulk_set_status(
        self, keys: Sequence[str], status: EventStatus, *, reason: str | None = None
    ) -> int:
        """Set the lifecycle status of many records at once. Returns rows affected."""

    @abstractmethod
    async def expire_ended(self, *, today: date) -> int:
        """Mark ACTIVE records that have ended (`end_date or start_date` < today) as
        EXPIRED. Never deletes. Returns the number newly expired."""

    @abstractmethod
    async def archive_before(self, *, cutoff: date) -> int:
        """Move EXPIRED records older than `cutoff` to ARCHIVED (the cold tier), keeping
        the hot working set bounded. Returns the number newly archived."""

    # --- reads --------------------------------------------------------------

    @abstractmethod
    async def search(self, criteria: SearchCriteria) -> Page:
        """Return one keyset page matching `criteria`, ordered by (start_date, key).
        `Page.next_cursor` drives the next page; memory is bounded by `criteria.limit`."""

    @abstractmethod
    def iterate(
        self, criteria: SearchCriteria, *, batch_size: int = 500
    ) -> AsyncIterator[StoredEvent]:
        """Stream every matching record in bounded batches (keyset internally). Never
        loads the full result set into memory — safe over millions of rows."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, key: str) -> StoredEvent | None:
        """Return a single stored event by key, or None."""

    @abstractmethod
    async def get_many(self, keys: Sequence[str]) -> dict[str, StoredEvent]:
        """Bulk-fetch records by key (e.g. dedup candidate lookup)."""

    @abstractmethod
    async def find_candidates(self, *, on_date: date, city: str | None = None) -> list[StoredEvent]:
        """Return ACTIVE records on `on_date` (optionally same city / online) — the
        blocked candidate set for write-time entity resolution."""

    @abstractmethod
    async def count(self, criteria: SearchCriteria) -> int:
        """Count records matching `criteria` (O(rows); use deliberately)."""

    # --- lifecycle ----------------------------------------------------------

    @abstractmethod
    async def close(self) -> None:
        """Release backend resources (connections, handles)."""
