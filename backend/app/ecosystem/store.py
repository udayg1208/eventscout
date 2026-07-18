"""Discovery-seed persistence (Phase 10D) — durable, incremental seed graph.

Persists the `SeedGraph` (the generated Discovery Seeds). ABC + InMemory (holds the live object) +
SQLite (`asyncio.to_thread` + lock + WAL; one JSON row per seed, keyed by (kind, canonical target)
so a re-run upserts rather than duplicates). Field-level provenance objects are not persisted; the
provenance *reason* and the relationship path are.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod

from app.ecosystem.models import ExpansionSeed, RelationshipPath, SeedGraph, SeedKind


class SeedStore(ABC):
    @abstractmethod
    async def save(self, seeds: SeedGraph) -> None: ...

    @abstractmethod
    async def load(self) -> SeedGraph | None: ...

    async def close(self) -> None:
        return None


class InMemorySeedStore(SeedStore):
    def __init__(self) -> None:
        self._seeds: SeedGraph | None = None

    async def save(self, seeds: SeedGraph) -> None:
        self._seeds = seeds

    async def load(self) -> SeedGraph | None:
        return self._seeds


def _row(seed: ExpansionSeed) -> tuple[str, str]:
    key = json.dumps(list(seed.dedup_key()))
    data = json.dumps(
        {
            "kind": seed.kind.value,
            "target": seed.target,
            "target_key": seed.target_key,
            "source": seed.source,
            "reason": seed.reason,
            "confidence": seed.confidence,
            "confidence_breakdown": seed.confidence_breakdown,
            "path": seed.path.as_dict(),
            "search_hint": seed.search_hint,
            "alt_paths": [p.as_dict() for p in seed.alt_paths],
        }
    )
    return key, data


class SQLiteSeedStore(SeedStore):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("CREATE TABLE IF NOT EXISTS seeds (id TEXT PRIMARY KEY, data TEXT)")
        self._conn.commit()

    async def save(self, seeds: SeedGraph) -> None:
        rows = [_row(s) for s in seeds.seeds.values()]

        def _save() -> None:
            with self._lock:
                self._conn.executemany("INSERT OR REPLACE INTO seeds VALUES (?,?)", rows)
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def load(self) -> SeedGraph | None:
        def _load():
            with self._lock:
                return self._conn.execute("SELECT data FROM seeds").fetchall()

        rows = await asyncio.to_thread(_load)
        if not rows:
            return None
        graph = SeedGraph()
        for (data,) in rows:
            d = json.loads(data)
            path = RelationshipPath(nodes=d["path"]["nodes"], relations=d["path"]["relations"])
            alt = [
                RelationshipPath(nodes=p["nodes"], relations=p["relations"])
                for p in d.get("alt_paths", [])
            ]
            seed = ExpansionSeed(
                kind=SeedKind(d["kind"]),
                target=d["target"],
                target_key=d["target_key"],
                source=d["source"],
                reason=d["reason"],
                confidence=d["confidence"],
                confidence_breakdown=d.get("confidence_breakdown", {}),
                path=path,
                search_hint=d.get("search_hint"),
                alt_paths=alt,
            )
            graph.seeds[seed.dedup_key()] = seed
        return graph

    async def count(self) -> int:
        def _c():
            with self._lock:
                return self._conn.execute("SELECT COUNT(*) FROM seeds").fetchone()[0]

        return await asyncio.to_thread(_c)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)
