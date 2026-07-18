"""Discovery Graph persistence (Phase 8C).

Persists the graph (nodes + edges) and expansion reports. Storage-agnostic (ABC + InMemory +
SQLite). `save_graph` snapshots the in-memory `ExpansionGraph`; `load_graph` rebuilds one — so the
graph survives runs and grows incrementally. Nothing here is destructive.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from abc import ABC, abstractmethod

from app.discovery.expansion.graph import ExpansionGraph
from app.discovery.expansion.models import EdgeType, GraphNode, NodeType


class ExpansionStore(ABC):
    @abstractmethod
    async def save_graph(self, graph: ExpansionGraph) -> None: ...

    @abstractmethod
    async def load_graph(self) -> ExpansionGraph: ...

    @abstractmethod
    async def save_report(self, report: dict) -> None: ...

    @abstractmethod
    async def latest_report(self) -> dict | None: ...

    async def close(self) -> None:
        return None


class InMemoryExpansionStore(ExpansionStore):
    def __init__(self) -> None:
        self._nodes: list[dict] = []
        self._edges: list[dict] = []
        self._reports: list[dict] = []

    async def save_graph(self, graph: ExpansionGraph) -> None:
        self._nodes = [n.as_dict() for n in graph.nodes()]
        self._edges = [e.as_dict() for e in graph.edges()]

    async def load_graph(self) -> ExpansionGraph:
        return _rebuild(self._nodes, self._edges)

    async def save_report(self, report: dict) -> None:
        self._reports.append(report)

    async def latest_report(self) -> dict | None:
        return self._reports[-1] if self._reports else None


def _rebuild(nodes: list[dict], edges: list[dict]) -> ExpansionGraph:
    g = ExpansionGraph()
    for n in nodes:
        g.upsert_node(
            GraphNode(
                key=n["key"],
                node_type=NodeType(n["node_type"]),
                url=n["url"],
                domain=n["domain"],
                title=n.get("title"),
                attrs=n.get("attrs", {}),
            )
        )
    for e in edges:
        g.add_edge(e["source"], e["target"], EdgeType(e["edge_type"]))
    return g


class SQLiteExpansionStore(ExpansionStore):
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS graph_nodes (key TEXT PRIMARY KEY, data TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS graph_edges (edge TEXT PRIMARY KEY, data TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS expansion_reports "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT)"
        )
        self._conn.commit()

    async def save_graph(self, graph: ExpansionGraph) -> None:
        def _save():
            with self._lock:
                for n in graph.nodes():
                    self._conn.execute(
                        "INSERT OR REPLACE INTO graph_nodes VALUES (?,?)",
                        (n.key, json.dumps(n.as_dict())),
                    )
                for e in graph.edges():
                    ek = f"{e.source}|{e.edge_type.value}|{e.target}"
                    self._conn.execute(
                        "INSERT OR REPLACE INTO graph_edges VALUES (?,?)",
                        (ek, json.dumps(e.as_dict())),
                    )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def load_graph(self) -> ExpansionGraph:
        def _load():
            with self._lock:
                nodes = [
                    json.loads(r[0]) for r in self._conn.execute("SELECT data FROM graph_nodes")
                ]
                edges = [
                    json.loads(r[0]) for r in self._conn.execute("SELECT data FROM graph_edges")
                ]
            return nodes, edges

        nodes, edges = await asyncio.to_thread(_load)
        return _rebuild(nodes, edges)

    async def save_report(self, report: dict) -> None:
        def _save():
            with self._lock:
                self._conn.execute(
                    "INSERT INTO expansion_reports (data) VALUES (?)", (json.dumps(report),)
                )
                self._conn.commit()

        await asyncio.to_thread(_save)

    async def latest_report(self) -> dict | None:
        def _get():
            with self._lock:
                row = self._conn.execute(
                    "SELECT data FROM expansion_reports ORDER BY id DESC LIMIT 1"
                ).fetchone()
            return json.loads(row[0]) if row else None

        return await asyncio.to_thread(_get)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)
