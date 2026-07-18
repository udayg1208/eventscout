"""Catalog wiring — the shared source of truth.

`get_repository()` and `get_state_store()` return process-wide singletons so the write
path (scheduler/ingestion) and the read path (search) operate on the *same* catalog. The
backend is chosen here from config (SQLite today, Postgres later) — nothing else in the app
constructs a concrete store.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.storage.provider_state import ProviderStateStore
from app.storage.repository import EventRepository
from app.storage.sqlite_provider_state import SQLiteProviderStateStore
from app.storage.sqlite_repository import SQLiteEventRepository


@lru_cache
def get_repository() -> EventRepository:
    """The event catalog — the single source of truth search reads from."""
    return SQLiteEventRepository(get_settings().catalog_db_path)


@lru_cache
def get_state_store() -> ProviderStateStore:
    """Per-provider ingestion state (used by the scheduler/engine)."""
    return SQLiteProviderStateStore(get_settings().provider_state_db_path)
