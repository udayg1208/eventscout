"""Organizer graph persistence (Phase 10C) — durable, incremental knowledge graph.

Persists the Organizer/Community/Series/Relationship graph (nodes + edges). ABC + InMemory (holds
the live object) + SQLite (`asyncio.to_thread` + lock + WAL; nodes and edges as JSON rows).
Supports incremental upserts so a re-run adds to the graph rather than rebuilding it.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod

from app.organizers.models import Edge, Node, NodeType, OrganizerGraph, RelationType


class GraphStore(ABC):
    @abstractmethod
    async def save(self, graph: OrganizerGraph) -> None: ...

    @abstractmethod
    async def load(self) -> OrganizerGraph | None: ...

    async def close(self) -> None:
        return None


class InMemoryGraphStore(GraphStore):
    def __init__(self) -> None:
        self._graph: OrganizerGraph | None = None

    async def save(self, graph: OrganizerGraph) -> None:
        self._graph = graph

    async def load(self) -> OrganizerGraph | None:
        return self._graph


def _node_row(n: Node) -> tuple[str, str]:
    return n.id, json.dumps(
        {
            "id": n.id,
            "type": n.type.value,
            "label": n.label,
            "attributes": n.attributes,
            "aliases": sorted(n.aliases),
        }
    )


def _edge_row(e: Edge) -> tuple[str, str]:
    return json.dumps(list(e.key())), json.dumps(
        {
            "source": e.source,
            "target": e.target,
            "relation": e.relation.value,
            "reason": e.reason,
            "weight": e.weight,
        }
    )


class SQLiteGraphStore(GraphStore):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("CREATE TABLE IF NOT EXISTS org_nodes (id TEXT PRIMARY KEY, data TEXT)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS org_edges (id TEXT PRIMARY KEY, data TEXT)")
        self._conn.commit()

    async def save(self, graph: OrganizerGraph) -> None:
        nodes = [_node_row(n) for n in graph.nodes.values()]
        edges = [_edge_row(e) for e in graph.edges.values()]

        def _save() -> None:
            with self._lock:
                self._conn.executemany("INSERT OR REPLACE INTO org_nodes VALUES (?,?)", nodes)
                self._conn.executemany("INSERT OR REPLACE INTO org_edges VALUES (?,?)", edges)
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def load(self) -> OrganizerGraph | None:
        def _load():
            with self._lock:
                nrows = self._conn.execute("SELECT data FROM org_nodes").fetchall()
                erows = self._conn.execute("SELECT data FROM org_edges").fetchall()
            return nrows, erows

        nrows, erows = await asyncio.to_thread(_load)
        if not nrows and not erows:
            return None
        graph = OrganizerGraph()
        for (data,) in nrows:
            d = json.loads(data)
            graph.nodes[d["id"]] = Node(
                id=d["id"],
                type=NodeType(d["type"]),
                label=d["label"],
                attributes=d.get("attributes", {}),
                aliases=set(d.get("aliases", [])),
            )
        for (data,) in erows:
            d = json.loads(data)
            e = Edge(
                d["source"],
                d["target"],
                RelationType(d["relation"]),
                d.get("reason", ""),
                d.get("weight", 1.0),
            )
            graph.edges[e.key()] = e
        return graph

    async def count(self) -> tuple[int, int]:
        def _c():
            with self._lock:
                n = self._conn.execute("SELECT COUNT(*) FROM org_nodes").fetchone()[0]
                e = self._conn.execute("SELECT COUNT(*) FROM org_edges").fetchone()[0]
            return n, e

        return await asyncio.to_thread(_c)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)
