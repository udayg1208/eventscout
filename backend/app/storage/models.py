"""Storage-layer models: the persisted record, its lifecycle, and read criteria.

Depends ONLY on the domain (`app.models.event`) — never on the provider or ingestion
layers — so the storage abstraction stays independent and the backend (SQLite now,
Postgres later) is swappable without touching anything else.

Designed for a catalog that scales to millions of records: identity is stable and
collision-resistant, reads are keyset-paginated (never offset), and the lifecycle is a
status enum (not a boolean) so expiry/withdrawal/archival are distinct, durable states.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from urllib.parse import urlsplit

from app.models.event import Event, EventCategory


class EventStatus(StrEnum):
    """Lifecycle of a stored record. Search shows ACTIVE; the rest are retained, not
    deleted (history is preserved)."""

    ACTIVE = "active"  # present in a source and not yet ended
    EXPIRED = "expired"  # ended (past) — kept for history/series/analytics
    WITHDRAWN = "withdrawn"  # a source removed it before it ended
    ARCHIVED = "archived"  # aged out of the hot set into the cold tier


def event_key(event: Event) -> str:
    """Stable, collision-resistant identity for an event — the repository primary key.

    Normally the canonicalized URL (`host + path`, lowercased, without scheme/`www.`/
    query/fragment/trailing slash): globally unique per event, so re-fetching the same
    event maps to the same key and upserts stay incremental. When the URL is host-only
    (a shared landing page with no per-event path), the URL is not a safe identity, so we
    disambiguate with a digest of `provider + title + start_date` — otherwise distinct
    events on one listing page would collapse into a single row. Self-contained so storage
    never imports the provider layer.
    """
    parts = urlsplit(str(event.url))
    host = parts.netloc.casefold().removeprefix("www.")
    path = parts.path.rstrip("/").casefold()
    if host and path:
        return f"{host}{path}"
    basis = f"{event.provider}|{event.title}|{event.start_date.isoformat()}".casefold()
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]
    return f"{host}#{digest}" if host else digest


def content_hash(event: Event) -> str:
    """SHA-256 over the event's meaningful fields. Upsert compares it against the stored
    hash to decide *unchanged* (a cheap touch) vs. *changed* (a rewrite + version bump).
    The field set and order are fixed so the hash is stable across runs and processes."""
    parts = [
        event.title,
        str(event.url),
        event.description or "",
        event.city or "",
        event.location or "",
        "1" if event.is_online else "0",
        event.start_date.isoformat(),
        event.end_date.isoformat() if event.end_date else "",
        event.category.value,
        "" if event.is_free is None else ("1" if event.is_free else "0"),
        event.price or "",
        event.provider,
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredEvent:
    """A persisted event: the immutable domain `Event` plus ingestion metadata.

    The domain model stays intact (the search path still receives the frozen `Event`);
    the surrounding fields are storage/ingestion concerns the domain must not carry.
    `version` increments each time the content changes (change history / auditing).
    """

    event: Event
    key: str
    content_hash: str
    first_seen_at: datetime
    last_seen_at: datetime
    status: EventStatus = EventStatus.ACTIVE
    status_reason: str | None = None
    version: int = 1

    @classmethod
    def from_event(
        cls,
        event: Event,
        *,
        seen_at: datetime,
        status: EventStatus = EventStatus.ACTIVE,
    ) -> StoredEvent:
        """Build a record from a freshly fetched event, stamped with the run time."""
        return cls(
            event=event,
            key=event_key(event),
            content_hash=content_hash(event),
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            status=status,
            version=1,
        )


@dataclass(frozen=True)
class UpsertResult:
    """Outcome of a bulk upsert — for logging, metrics, and tests."""

    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.unchanged


@dataclass(frozen=True)
class Page:
    """A single keyset page of results. `next_cursor` is an opaque token for the next
    page (None when exhausted). `total` is populated only when explicitly requested —
    counting is O(rows) and avoided on the hot path."""

    items: list[StoredEvent]
    next_cursor: str | None = None
    total: int | None = None


@dataclass
class SearchCriteria:
    """Storage-layer query. Mirrors `SearchQuery`'s filters and adds storage-only concerns
    (`active_only`, `upcoming_on_or_after`, keyset `cursor`, `limit`). The
    `DatabaseSearchProvider` (3E) translates a frozen `SearchQuery` into this, so the
    repository never depends on the query model. Every field defaults to "no constraint"."""

    keywords: list[str] = field(default_factory=list)
    city: str | None = None
    categories: list[EventCategory] = field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    free_only: bool = False
    active_only: bool = True  # ACTIVE status only
    upcoming_on_or_after: date | None = None
    cursor: str | None = None  # keyset pagination position (opaque)
    limit: int | None = None


# --------------------------- keyset cursor ---------------------------

# The catalog is ordered by (start_date, key); a cursor is exactly that pair, so the next
# page is "everything strictly after it". Keyset paging stays O(limit) at any depth,
# unlike OFFSET which degrades linearly — this is what lets search scale to millions.


def encode_cursor(start_date: date, key: str) -> str:
    raw = f"{start_date.isoformat()}|{key}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[date, str]:
    raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    iso, _, key = raw.partition("|")
    return date.fromisoformat(iso), key
