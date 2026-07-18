"""The Discovery Graph (Phase 8C) — persistent nodes + typed edges.

Every discovered object (page, domain, feed, calendar, community, GitHub org, Notion site, …) is a
node; relationships (links_to / owns / hosts / contains_feed / …) are edges. Nodes dedup by their
canonical key, edges by (source, target, type) — so re-discovery merges rather than duplicates. In
memory here; a persistent backend is a thin add (see store.py).
"""

from __future__ import annotations

from app.discovery.expansion.models import EdgeType, GraphEdge, GraphNode, NodeType


class ExpansionGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: set[GraphEdge] = set()

    def upsert_node(self, node: GraphNode) -> tuple[GraphNode, bool]:
        """Insert or merge by key. Returns (node, added?)."""
        existing = self._nodes.get(node.key)
        if existing is None:
            self._nodes[node.key] = node
            return node, True
        if node.last_seen_at:
            existing.last_seen_at = node.last_seen_at
        if node.title and not existing.title:
            existing.title = node.title
        existing.attrs.update({k: v for k, v in node.attrs.items() if v is not None})
        return existing, False

    def add_edge(self, source_key: str, target_key: str, edge_type: EdgeType) -> bool:
        edge = GraphEdge(source_key, target_key, edge_type)
        if edge in self._edges:
            return False
        self._edges.add(edge)
        return True

    def get(self, key: str) -> GraphNode | None:
        return self._nodes.get(key)

    def nodes(self) -> list[GraphNode]:
        return list(self._nodes.values())

    def edges(self) -> list[GraphEdge]:
        return list(self._edges)

    def neighbors(self, key: str, *, edge_type: EdgeType | None = None) -> list[GraphNode]:
        out = []
        for e in self._edges:
            if e.source == key and (edge_type is None or e.edge_type is edge_type):
                node = self._nodes.get(e.target)
                if node:
                    out.append(node)
        return out

    def nodes_of(self, node_type: NodeType) -> list[GraphNode]:
        return [n for n in self._nodes.values() if n.node_type is node_type]

    def stats(self) -> dict:
        by_node: dict[str, int] = {}
        for n in self._nodes.values():
            by_node[n.node_type.value] = by_node.get(n.node_type.value, 0) + 1
        by_edge: dict[str, int] = {}
        for e in self._edges:
            by_edge[e.edge_type.value] = by_edge.get(e.edge_type.value, 0) + 1
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "nodes_by_type": by_node,
            "edges_by_type": by_edge,
        }
