"""Social-extraction persistence (Phase 8D).

The Discovery Inbox candidate carries the distilled verdict; the full provenance-bearing record
(every field's snippet/reason/confidence, the priority breakdown, the safety verdict) lives here,
keyed by url — nothing opaque. ABC + InMemory + SQLite, mirroring the D4 AIExtractionStore.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SocialRecord:
    url: str
    platform: str
    extraction: dict
    priority: dict
    safety: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "platform": self.platform,
            "extraction": self.extraction,
            "priority": self.priority,
            "safety": self.safety,
        }


class SocialStore(ABC):
    @abstractmethod
    async def save(self, record: SocialRecord) -> None: ...

    @abstractmethod
    async def get(self, url: str) -> SocialRecord | None: ...

    @abstractmethod
    async def count(self) -> int: ...

    async def close(self) -> None:
        return None


class InMemorySocialStore(SocialStore):
    def __init__(self) -> None:
        self._rows: dict[str, SocialRecord] = {}

    async def save(self, record: SocialRecord) -> None:
        self._rows[record.url] = record

    async def get(self, url: str) -> SocialRecord | None:
        return self._rows.get(url)

    async def count(self) -> int:
        return len(self._rows)


class SQLiteSocialStore(SocialStore):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS social_records "
            "(url TEXT PRIMARY KEY, platform TEXT, data TEXT)"
        )
        self._conn.commit()

    async def save(self, record: SocialRecord) -> None:
        def _save():
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO social_records VALUES (?,?,?)",
                    (record.url, record.platform, json.dumps(record.as_dict())),
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def get(self, url: str) -> SocialRecord | None:
        def _get():
            with self._lock:
                row = self._conn.execute(
                    "SELECT data FROM social_records WHERE url=?", (url,)
                ).fetchone()
            return row

        row = await asyncio.to_thread(_get)
        if not row:
            return None
        d = json.loads(row[0])
        return SocialRecord(
            url=d["url"],
            platform=d["platform"],
            extraction=d["extraction"],
            priority=d["priority"],
            safety=d.get("safety", {}),
        )

    async def count(self) -> int:
        def _c():
            with self._lock:
                return self._conn.execute("SELECT COUNT(*) FROM social_records").fetchone()[0]

        return await asyncio.to_thread(_c)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)
