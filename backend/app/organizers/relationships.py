"""Relationship discovery (Phase 10C) — expand one organizer into its ecosystem graph.

Given an organizer profile already extracted from a page, materialise the surrounding nodes and
edges: its website(s), calendars, feeds, GitHub/Discord/Telegram/LinkedIn/Notion channels, chapter
parent, university/department, recurring series, sponsors, and venue. This is the auto-expansion —
one organizer becomes a connected subgraph. Deterministic; uses only what extraction already found
(no network).
"""

from __future__ import annotations

from app.organizers.identity import canonical_key
from app.organizers.models import (
    Edge,
    Node,
    NodeType,
    OrganizerGraph,
    OrganizerProfile,
    RelationType,
)
from app.universal.provenance import known  # noqa: F401  (kept for symmetry / future use)

_SOCIAL_TYPE = {
    "github": NodeType.GITHUB_ORG,
    "discord": NodeType.DISCORD,
    "telegram": NodeType.TELEGRAM,
    "linkedin": NodeType.LINKEDIN_PAGE,
    "notion": NodeType.NOTION_WORKSPACE,
}


def _nid(prefix: str, value: str) -> str:
    return f"{prefix}:{value.strip().lower()}"


class RelationshipDiscoverer:
    def expand(self, graph: OrganizerGraph, org_id: str, profile: OrganizerProfile) -> list[str]:
        """Materialise the organizer's ecosystem; return the ids of newly-linked nodes."""
        added: list[str] = []

        def link(node: Node, relation: RelationType, reason: str, *, reverse: bool = False) -> None:
            graph.add_node(node)
            edge = (
                Edge(node.id, org_id, relation, reason)
                if reverse
                else Edge(org_id, node.id, relation, reason)
            )
            graph.add_edge(edge)
            added.append(node.id)

        # chapter parent (e.g. GDG Bangalore CHAPTER_OF Google Developer Group)
        parent = profile.get("parent_org")
        if parent:
            pid = _nid("org", canonical_key(parent))
            rel = RelationType.CHAPTER_OF if profile.get("chapter") else RelationType.BELONGS_TO
            link(Node(pid, NodeType.ORGANIZATION, parent), rel, "declared parent/chapter")

        # university + department
        uni = profile.get("university")
        if uni:
            link(
                Node(_nid("uni", canonical_key(uni)), NodeType.UNIVERSITY, uni),
                RelationType.BELONGS_TO,
                "campus organizer",
            )
        dept = profile.get("department")
        if dept:
            link(
                Node(_nid("dept", canonical_key(dept)), NodeType.DEPARTMENT, dept),
                RelationType.BELONGS_TO,
                "department",
            )

        # recurring series
        for s in profile.get("series") or []:
            sid = _nid("series", canonical_key(s))
            link(
                Node(sid, NodeType.CONFERENCE_SERIES, s, attributes={"recurring": True}),
                RelationType.ORGANIZES,
                "runs recurring series",
            )
            graph.add_edge(Edge(sid, sid, RelationType.RECURRING, "recurring series"))

        # sponsors (sponsor SPONSORS organizer)
        for sp in profile.get("sponsors") or []:
            link(
                Node(_nid("sponsor", canonical_key(sp)), NodeType.SPONSOR, sp),
                RelationType.SPONSORS,
                "declared sponsor",
                reverse=True,
            )

        # venue
        venue = profile.get("venue")
        if venue:
            link(
                Node(_nid("venue", canonical_key(venue)), NodeType.VENUE, venue),
                RelationType.HOSTS,
                "event venue",
            )

        # calendars / feeds
        for cal in profile.get("calendars") or []:
            link(
                Node(_nid("cal", cal), NodeType.CALENDAR, cal),
                RelationType.USES_CALENDAR,
                "calendar link",
            )
        for feed in profile.get("feeds") or []:
            link(Node(_nid("feed", feed), NodeType.FEED, feed), RelationType.USES_FEED, "feed link")

        # websites (domains)
        for dom in profile.get("domains") or []:
            link(
                Node(_nid("web", dom), NodeType.WEBSITE, dom),
                RelationType.ANNOUNCES_ON,
                "website domain",
            )

        # social channels
        socials = profile.get("social_pages") or {}
        for platform, url in socials.items():
            ntype = _SOCIAL_TYPE.get(platform, NodeType.WEBSITE)
            link(
                Node(_nid(platform, url), ntype, url, attributes={"platform": platform}),
                RelationType.ANNOUNCES_ON,
                f"{platform} channel",
            )

        return added
