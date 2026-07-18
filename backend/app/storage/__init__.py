"""Storage layer — the persistent source of truth.

`EventRepository` is the storage-agnostic abstraction the rest of the app depends on.
`SQLiteEventRepository` is the first implementation; a Postgres/Supabase backend will be
a drop-in second implementation of the same interface.
"""

from app.storage.models import (
    EventStatus,
    Page,
    SearchCriteria,
    StoredEvent,
    UpsertResult,
    content_hash,
    event_key,
)
from app.storage.provider_state import (
    CircuitState,
    HealthStatus,
    HealthSummary,
    ProviderState,
    ProviderStateStore,
    RetryPolicy,
)
from app.storage.repository import EventRepository
from app.storage.sqlite_provider_state import SQLiteProviderStateStore
from app.storage.sqlite_repository import SQLiteEventRepository

__all__ = [
    # catalog
    "EventRepository",
    "SQLiteEventRepository",
    "StoredEvent",
    "EventStatus",
    "SearchCriteria",
    "Page",
    "UpsertResult",
    "content_hash",
    "event_key",
    # provider state
    "ProviderStateStore",
    "SQLiteProviderStateStore",
    "ProviderState",
    "CircuitState",
    "HealthStatus",
    "HealthSummary",
    "RetryPolicy",
]
