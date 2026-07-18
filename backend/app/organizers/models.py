"""Organizer & Community Intelligence models (Phase 10C).

This phase discovers *organizers* — the people, orgs, clubs, chapters, communities and recurring
ecosystems that continuously generate events — not individual events. The output is an **Organizer
Graph** (typed nodes + typed edges), never Event objects. Every extracted field carries provenance
(reused from D4 via 10B's helpers); UNKNOWN is preferred over a guess. Additive; no network, no
browser, no LLM; discovery only — nothing is written to the catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.discovery.ai.models import ExtractedField, Provenance


class NodeType(StrEnum):
    ORGANIZATION = "organization"
    COMMUNITY = "community"
    MEETUP_GROUP = "meetup_group"
    UNIVERSITY_CLUB = "university_club"
    UNIVERSITY = "university"
    DEPARTMENT = "department"
    CHAPTER = "chapter"
    STUDENT_CHAPTER = "student_chapter"
    PROFESSIONAL_SOCIETY = "professional_society"
    CONFERENCE_SERIES = "conference_series"
    RECURRING_EVENT = "recurring_event"
    SPONSOR = "sponsor"
    VENUE = "venue"
    WEBSITE = "website"
    CALENDAR = "calendar"
    FEED = "feed"
    GITHUB_ORG = "github_org"
    NOTION_WORKSPACE = "notion_workspace"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    LINKEDIN_PAGE = "linkedin_page"


class RelationType(StrEnum):
    ORGANIZES = "organizes"
    HOSTS = "hosts"
    BELONGS_TO = "belongs_to"
    CHAPTER_OF = "chapter_of"
    SPONSORS = "sponsors"
    USES_CALENDAR = "uses_calendar"
    USES_FEED = "uses_feed"
    ANNOUNCES_ON = "announces_on"
    MEMBER_OF = "member_of"
    PARTNER_OF = "partner_of"
    SAME_COMMUNITY = "same_community"
    SAME_SERIES = "same_series"
    RECURRING = "recurring"


class Health(StrEnum):
    NEW = "new"
    ACTIVE = "active"
    SEASONAL = "seasonal"
    DORMANT = "dormant"
    INACTIVE = "inactive"


class Cadence(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    UNKNOWN = "unknown"


# The organizer profile schema — the phase brief's extraction field list.
ORGANIZER_FIELDS: tuple[str, ...] = (
    "name",
    "aliases",
    "parent_org",
    "chapter",
    "university",
    "department",
    "community",
    "series",
    "sponsors",
    "venue",
    "domains",
    "calendars",
    "feeds",
    "social_pages",
    "city",
    "technologies",
)

_CADENCE_DAYS = {
    Cadence.WEEKLY: 7,
    Cadence.MONTHLY: 31,
    Cadence.QUARTERLY: 93,
    Cadence.ANNUAL: 366,
    Cadence.UNKNOWN: 0,
}


def cadence_days(c: Cadence) -> int:
    return _CADENCE_DAYS[c]


@dataclass
class OrganizerProfile:
    """A provenance-bearing organizer profile extracted from a page/event."""

    fields: dict[str, ExtractedField] = field(default_factory=dict)
    node_type: NodeType = NodeType.ORGANIZATION

    def get(self, name: str):
        f = self.fields.get(name)
        return f.value if (f and f.is_known) else None

    @property
    def name(self) -> str | None:
        return self.get("name")

    def known_fields(self) -> list[str]:
        return [n for n in ORGANIZER_FIELDS if n in self.fields and self.fields[n].is_known]

    def as_dict(self) -> dict:
        out: dict = {"node_type": self.node_type.value, "fields": {}}
        for name in ORGANIZER_FIELDS:
            f = self.fields.get(name)
            if f and f.is_known:
                out["fields"][name] = {
                    "value": f.value,
                    "status": f.status.value,
                    "confidence": round(f.confidence, 3),
                    "reason": f.provenance.reason if f.provenance else None,
                }
        return out


@dataclass
class Node:
    id: str  # canonical identity key
    type: NodeType
    label: str
    attributes: dict = field(default_factory=dict)
    aliases: set[str] = field(default_factory=set)
    provenance: dict[str, Provenance] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "label": self.label,
            "attributes": self.attributes,
            "aliases": sorted(self.aliases),
            "provenance": {k: v.reason for k, v in self.provenance.items()},
        }


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    relation: RelationType
    reason: str = ""
    weight: float = 1.0

    def key(self) -> tuple[str, str, str]:
        return (self.source, self.relation.value, self.target)

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation.value,
            "reason": self.reason,
            "weight": round(self.weight, 3),
        }


@dataclass
class OrganizerGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[tuple[str, str, str], Edge] = field(default_factory=dict)

    # -- mutation (incremental) ---------------------------------------------

    def add_node(self, node: Node) -> Node:
        existing = self.nodes.get(node.id)
        if existing is None:
            self.nodes[node.id] = node
            return node
        # incremental merge: union aliases/attributes/provenance, keep richest label
        existing.aliases |= node.aliases
        if len(node.label) > len(existing.label):
            existing.label = node.label
        for k, v in node.attributes.items():
            existing.attributes.setdefault(k, v)
        for k, v in node.provenance.items():
            existing.provenance.setdefault(k, v)
        if existing.type is NodeType.WEBSITE and node.type is not NodeType.WEBSITE:
            existing.type = node.type  # a specific type beats a generic website
        return existing

    def add_edge(self, edge: Edge) -> Edge:
        return self.edges.setdefault(edge.key(), edge)

    def merge_nodes(self, keep_id: str, drop_id: str) -> None:
        """Fold `drop_id` into `keep_id` — reassign edges, union aliases."""
        if keep_id == drop_id or drop_id not in self.nodes:
            return
        keep = self.nodes[keep_id]
        drop = self.nodes.pop(drop_id)
        keep.aliases |= drop.aliases | {drop.label}
        for k, v in drop.attributes.items():
            keep.attributes.setdefault(k, v)
        rebuilt: dict[tuple[str, str, str], Edge] = {}
        for edge in self.edges.values():
            s = keep_id if edge.source == drop_id else edge.source
            t = keep_id if edge.target == drop_id else edge.target
            if s == t:
                continue
            e = Edge(s, t, edge.relation, edge.reason, edge.weight)
            rebuilt[e.key()] = e
        self.edges = rebuilt

    # -- queries ------------------------------------------------------------

    def neighbors(self, node_id: str, relation: RelationType | None = None) -> list[Node]:
        out: list[Node] = []
        for edge in self.edges.values():
            if edge.source == node_id and (relation is None or edge.relation is relation):
                target = self.nodes.get(edge.target)
                if target:
                    out.append(target)
        return out

    def nodes_of(self, *types: NodeType) -> list[Node]:
        want = set(types)
        return [n for n in self.nodes.values() if n.type in want]

    def edges_of(self, *relations: RelationType) -> list[Edge]:
        want = set(relations)
        return [e for e in self.edges.values() if e.relation in want]

    def subgraph(self, node_types: set[NodeType], edge_types: set[RelationType]) -> OrganizerGraph:
        sub = OrganizerGraph()
        for n in self.nodes.values():
            if n.type in node_types:
                sub.nodes[n.id] = n
        for e in self.edges.values():
            if e.relation in edge_types and e.source in sub.nodes and e.target in sub.nodes:
                sub.edges[e.key()] = e
        return sub

    # -- named views (persisted graphs) -------------------------------------

    def community_view(self) -> OrganizerGraph:
        return self.subgraph(
            {
                NodeType.ORGANIZATION,
                NodeType.COMMUNITY,
                NodeType.MEETUP_GROUP,
                NodeType.UNIVERSITY_CLUB,
                NodeType.CHAPTER,
                NodeType.STUDENT_CHAPTER,
                NodeType.PROFESSIONAL_SOCIETY,
            },
            {
                RelationType.SAME_COMMUNITY,
                RelationType.CHAPTER_OF,
                RelationType.BELONGS_TO,
                RelationType.MEMBER_OF,
                RelationType.PARTNER_OF,
            },
        )

    def series_view(self) -> OrganizerGraph:
        return self.subgraph(
            {
                NodeType.CONFERENCE_SERIES,
                NodeType.RECURRING_EVENT,
                NodeType.ORGANIZATION,
                NodeType.COMMUNITY,
            },
            {
                RelationType.SAME_SERIES,
                RelationType.RECURRING,
                RelationType.ORGANIZES,
                RelationType.HOSTS,
            },
        )

    def as_dict(self) -> dict:
        return {
            "nodes": [n.as_dict() for n in self.nodes.values()],
            "edges": [e.as_dict() for e in self.edges.values()],
            "counts": {
                "nodes": len(self.nodes),
                "edges": len(self.edges),
                "by_type": self._by_type(),
            },
        }

    def _by_type(self) -> dict:
        counts: dict[str, int] = {}
        for n in self.nodes.values():
            counts[n.type.value] = counts.get(n.type.value, 0) + 1
        return counts
