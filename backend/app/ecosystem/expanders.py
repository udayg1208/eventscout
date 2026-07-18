"""The seven isolated expanders (Phase 10D).

Each takes an `ExpansionContext` (a source organizer + its 10C profile + the graph + the path so
far) and returns `ExpansionSeed`s — new ecosystems to discover, with a relationship path and
explainable confidence. Chapter/series fan a family across cities; sponsor maps a sponsor to its
programs; university/venue emit the standard campus club set; similar-organizer uses 10C
similarity; connected- resource walks the organizer's own ecosystem edges. Deterministic; generates
*seeds to check*, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.discovery.ai.models import ExtractionMethod, Provenance
from app.ecosystem.confidence import ExpansionConfidence
from app.ecosystem.dedup import canonical_target
from app.ecosystem.models import ExpansionBudget, ExpansionSeed, RelationshipPath, SeedKind
from app.ecosystem.templates import (
    CHAPTER_DISPLAY,
    CITIES,
    SERIES_CADENCE,
    SPONSOR_PROGRAMS,
    UNIVERSITY_UNITS,
    sponsor_key,
)
from app.organizers.models import OrganizerGraph, OrganizerProfile
from app.organizers.similarity import CommunitySimilarity

_CONF = ExpansionConfidence()
_SIM = CommunitySimilarity()

_REL_STRENGTH = {
    "chapter_of": 0.9,
    "organizes": 0.9,
    "recurring": 0.85,
    "sponsors": 0.7,
    "hosts": 0.7,
    "belongs_to": 0.7,
    "member_of": 0.7,
    "uses_calendar": 0.6,
    "uses_feed": 0.6,
    "announces_on": 0.55,
    "same_community": 0.6,
    "same_series": 0.65,
}
_CAMPUS = ("university", "college", "institute", "iit", "nit", "iiit", "campus", "school of")


def _prov(reason: str, snippet: str, conf: float) -> Provenance:
    return Provenance(
        source_snippet=snippet[:200],
        reason=reason,
        confidence=round(max(0.0, min(1.0, conf)), 3),
        method=ExtractionMethod.DETERMINISTIC,
    )


def _jaccard(a, b) -> float:
    sa, sb = {str(x).lower() for x in (a or [])}, {str(x).lower() for x in (b or [])}
    return len(sa & sb) / len(sa | sb) if (sa and sb) else 0.0


@dataclass
class ExpansionContext:
    source_id: str
    profile: OrganizerProfile
    graph: OrganizerGraph = field(default_factory=OrganizerGraph)
    base_path: RelationshipPath = field(default_factory=RelationshipPath)
    peers: dict[str, OrganizerProfile] = field(default_factory=dict)

    def source_name(self) -> str:
        return self.profile.get("name") or self.source_id


def _seed(kind, target, ctx, *, reason, path, cs, hint=None) -> ExpansionSeed:
    return ExpansionSeed(
        kind=kind,
        target=target,
        target_key=canonical_target(target),
        source=ctx.source_id,
        reason=reason,
        confidence=cs.total,
        confidence_breakdown=cs.components,
        provenance=_prov(reason, ctx.source_name(), cs.total),
        path=path,
        search_hint=hint,
    )


class ChapterExpander:
    """GDG Bangalore → GDG Delhi / Mumbai / Jaipur / … (sibling chapters in other cities)."""

    def expand(self, ctx: ExpansionContext, budget: ExpansionBudget) -> list[ExpansionSeed]:
        chapter = ctx.profile.get("chapter")
        display = CHAPTER_DISPLAY.get(chapter) if chapter else None
        if not display:
            return []
        src_city = (ctx.profile.get("city") or "").lower()
        techs = ctx.profile.get("technologies")
        recurring = 1.0 if ctx.profile.get("series") else 0.0
        out: list[ExpansionSeed] = []
        for city in CITIES:
            if city.lower() == src_city:
                continue
            target = f"{display} {city}"
            cs = _CONF.score(
                depth=1,
                relationship_strength=0.9,
                chapter_overlap=1.0,
                organizer_overlap=0.5,
                technology_overlap=(0.8 if techs else 0.0),
                recurring=recurring,
            )
            path = ctx.base_path.extend("same_chapter", target)
            out.append(
                _seed(
                    SeedKind.CHAPTER_SIBLING,
                    target,
                    ctx,
                    reason=f"sibling of the {display} chapter family in {city}",
                    path=path,
                    cs=cs,
                    hint=f"{target} tech community",
                )
            )
            if len(out) >= budget.max_branches:
                break
        return out


class SeriesExpander:
    """DevFest → DevFest Bangalore / Delhi / Jaipur … (series instances across cities)."""

    def expand(self, ctx: ExpansionContext, budget: ExpansionBudget) -> list[ExpansionSeed]:
        series = ctx.profile.get("series") or []
        if not series:
            return []
        src_city = (ctx.profile.get("city") or "").lower()
        techs = ctx.profile.get("technologies")
        out: list[ExpansionSeed] = []
        for brand in series:
            for city in CITIES:
                if city.lower() == src_city:
                    continue
                target = f"{brand} {city}"
                cs = _CONF.score(
                    depth=1,
                    relationship_strength=0.85,
                    recurring=1.0,
                    chapter_overlap=0.5,
                    technology_overlap=(0.7 if techs else 0.0),
                    organizer_overlap=0.3,
                )
                path = ctx.base_path.extend("same_series", target)
                out.append(
                    _seed(
                        SeedKind.SERIES_INSTANCE,
                        target,
                        ctx,
                        reason=f"instance of the recurring '{brand}' series in {city}",
                        path=path,
                        cs=cs,
                        hint=f"{target} event",
                    )
                )
                if len(out) >= budget.max_branches:
                    return out
        return out


class SponsorExpander:
    """Google sponsors GDG → Google Developers / Build with AI / Cloud Arcade (sponsor programs)."""

    def expand(self, ctx: ExpansionContext, budget: ExpansionBudget) -> list[ExpansionSeed]:
        sponsors = ctx.profile.get("sponsors") or []
        techs = ctx.profile.get("technologies")
        out: list[ExpansionSeed] = []
        for sponsor in sponsors:
            key = sponsor_key(sponsor)
            programs = SPONSOR_PROGRAMS.get(key, []) if key else []
            if not programs:
                target = f"{sponsor} Developer Community"
                cs = _CONF.score(
                    depth=2,
                    relationship_strength=0.5,
                    sponsor_overlap=1.0,
                    technology_overlap=(0.4 if techs else 0.0),
                )
                path = ctx.base_path.extend("sponsors", sponsor).extend("community", target)
                out.append(
                    _seed(
                        SeedKind.SPONSOR_PROGRAM,
                        target,
                        ctx,
                        reason=f"{sponsor} runs developer programs/communities",
                        path=path,
                        cs=cs,
                        hint=f"{sponsor} developer community India",
                    )
                )
                continue
            for program, prog_techs in programs:
                recurring = 1.0 if program in SERIES_CADENCE else 0.0
                cs = _CONF.score(
                    depth=2,
                    relationship_strength=0.7,
                    sponsor_overlap=1.0,
                    technology_overlap=_jaccard(techs, prog_techs),
                    recurring=recurring,
                )
                path = ctx.base_path.extend("sponsors", sponsor).extend("runs_program", program)
                out.append(
                    _seed(
                        SeedKind.SPONSOR_PROGRAM,
                        program,
                        ctx,
                        reason=f"program run by sponsor {sponsor}",
                        path=path,
                        cs=cs,
                        hint=f"{program} India",
                    )
                )
                if len(out) >= budget.max_branches:
                    return out
        return out


def _campus_units(ctx, budget, institution: str, kind: SeedKind, via: str) -> list[ExpansionSeed]:
    techs = ctx.profile.get("technologies")
    out: list[ExpansionSeed] = []
    for unit, unit_techs, _ntype in UNIVERSITY_UNITS:
        target = f"{unit}, {institution}"
        cs = _CONF.score(
            depth=2,
            relationship_strength=0.65,
            organizer_overlap=0.4,
            technology_overlap=_jaccard(techs, unit_techs),
        )
        path = ctx.base_path.extend(via, institution).extend("has_unit", unit)
        out.append(
            _seed(
                kind,
                target,
                ctx,
                reason=f"standard campus club at {institution}",
                path=path,
                cs=cs,
                hint=f"{unit} {institution}",
            )
        )
        if len(out) >= budget.max_branches:
            break
    return out


class UniversityExpander:
    """IIIT Delhi → ACM Chapter / IEEE Branch / GDSC / E-Cell / Robotics Club / … (campus units)."""

    def expand(self, ctx: ExpansionContext, budget: ExpansionBudget) -> list[ExpansionSeed]:
        uni = ctx.profile.get("university")
        return (
            _campus_units(ctx, budget, uni, SeedKind.UNIVERSITY_UNIT, "belongs_to") if uni else []
        )


class VenueExpander:
    """A campus venue → the clubs/departments/labs it hosts."""

    def expand(self, ctx: ExpansionContext, budget: ExpansionBudget) -> list[ExpansionSeed]:
        venue = ctx.profile.get("venue") or ""
        if not any(w in venue.lower() for w in _CAMPUS):
            return []
        return _campus_units(ctx, budget, venue, SeedKind.VENUE_UNIT, "hosts")


class SimilarOrganizerExpander:
    """Recommend nearby communities by deterministic 10C similarity."""

    def __init__(self, threshold: float = 0.25) -> None:
        self._threshold = threshold

    def expand(self, ctx: ExpansionContext, budget: ExpansionBudget) -> list[ExpansionSeed]:
        out: list[ExpansionSeed] = []
        ranked = []
        for pid, peer in ctx.peers.items():
            if pid == ctx.source_id:
                continue
            s = _SIM.score(ctx.profile, peer)
            if s.total >= self._threshold:
                ranked.append((s, peer))
        ranked.sort(key=lambda x: -x[0].total)
        for s, peer in ranked[: budget.max_branches]:
            name = peer.get("name") or "unknown"
            cs = _CONF.score(
                depth=1,
                relationship_strength=s.total,
                chapter_overlap=s.components["same_chapter"],
                organizer_overlap=s.components["same_organizer"],
                technology_overlap=s.components["same_technologies"],
            )
            path = ctx.base_path.extend("similar_to", name)
            out.append(
                _seed(
                    SeedKind.SIMILAR_ORGANIZER,
                    name,
                    ctx,
                    reason=f"deterministically similar community (score {s.total:.2f})",
                    path=path,
                    cs=cs,
                    hint=name,
                )
            )
        return out


class ConnectedResourceExpander:
    """Discover every public resource connected to the organizer (website/github/discord/feed/…)."""

    def expand(self, ctx: ExpansionContext, budget: ExpansionBudget) -> list[ExpansionSeed]:
        out: list[ExpansionSeed] = []
        seen: set[str] = set()
        for edge in ctx.graph.edges.values():
            other_id, rel = None, edge.relation.value
            if edge.source == ctx.source_id:
                other_id = edge.target
            elif edge.target == ctx.source_id:
                other_id = edge.source
            if other_id is None or other_id in seen or other_id == ctx.source_id:
                continue
            node = ctx.graph.nodes.get(other_id)
            if node is None:
                continue
            seen.add(other_id)
            cs = _CONF.score(
                depth=1, relationship_strength=_REL_STRENGTH.get(rel, 0.5), organizer_overlap=0.5
            )
            path = ctx.base_path.extend(rel, node.label)
            out.append(
                _seed(
                    SeedKind.CONNECTED_RESOURCE,
                    node.label,
                    ctx,
                    reason=f"public resource connected via '{rel}'",
                    path=path,
                    cs=cs,
                    hint=node.label,
                )
            )
            if len(out) >= budget.max_branches:
                break
        return out


ALL_EXPANDERS = [
    ConnectedResourceExpander(),
    ChapterExpander(),
    SeriesExpander(),
    SponsorExpander(),
    UniversityExpander(),
    VenueExpander(),
    SimilarOrganizerExpander(),
]
