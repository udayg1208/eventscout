"""Phase 10D — Ecosystem Expansion tests. Fixtures only, NO network/browser/LLM."""

from __future__ import annotations

import asyncio

from app.ecosystem import (
    DEFAULT_BUDGET,
    ChapterExpander,
    ConnectedResourceExpander,
    EcosystemExpansionEngine,
    ExpansionBudget,
    ExpansionConfidence,
    ExpansionContext,
    ExpansionSeed,
    InMemorySeedStore,
    RelationshipPath,
    SeedDeduplicator,
    SeedGraph,
    SeedKind,
    SeriesExpander,
    SimilarOrganizerExpander,
    SponsorExpander,
    SQLiteSeedStore,
    UniversityExpander,
    VenueExpander,
    canonical_target,
)
from app.ecosystem.confidence import WEIGHTS as CONF_WEIGHTS
from app.ecosystem.templates import (
    CHAPTER_DISPLAY,
    CITIES,
    SPONSOR_PROGRAMS,
    UNIVERSITY_UNITS,
    sponsor_key,
)
from app.organizers import Edge, Node, NodeType, OrganizerGraph, OrganizerProfile, RelationType
from app.universal.provenance import known


def run(coro):
    return asyncio.run(coro)


def profile(**kw) -> OrganizerProfile:
    fields = {k: known(v, snippet="s", reason="r", confidence=0.8) for k, v in kw.items()}
    return OrganizerProfile(fields=fields)


def ctx(prof, *, graph=None, peers=None, source="org:x") -> ExpansionContext:
    return ExpansionContext(
        source_id=source,
        profile=prof,
        graph=graph or OrganizerGraph(),
        base_path=RelationshipPath(nodes=[prof.get("name") or source]),
        peers=peers or {},
    )


def seed(kind=SeedKind.CHAPTER_SIBLING, target="GDG Delhi", conf=0.6, path=None) -> ExpansionSeed:
    return ExpansionSeed(
        kind=kind,
        target=target,
        target_key=canonical_target(target),
        source="org:x",
        reason="r",
        confidence=conf,
        path=path or RelationshipPath(nodes=["A", target]),
    )


# --------------------------------------------------------------------------- models


def test_relationship_path_extend_render_depth():
    p = RelationshipPath(nodes=["A"]).extend("sponsors", "B").extend("runs", "C")
    assert p.depth == 2
    assert p.render() == "A --[sponsors]--> B --[runs]--> C"
    assert p.as_dict()["depth"] == 2


def test_relationship_path_empty_render():
    assert RelationshipPath().render() == ""


def test_seed_dedup_key_and_as_dict():
    s = seed()
    assert s.dedup_key() == ("chapter_sibling", canonical_target("GDG Delhi"))
    d = s.as_dict()
    assert d["kind"] == "chapter_sibling" and d["target"] == "GDG Delhi" and "path" in d


def test_seedgraph_add_and_merge():
    g = SeedGraph()
    assert g.add(seed(conf=0.5)) == "added"
    assert g.add(seed(conf=0.7, path=RelationshipPath(nodes=["Z", "GDG Delhi"]))) == "merged"
    assert len(g.seeds) == 1
    only = g.all()[0]
    assert only.confidence == 0.7  # strongest kept
    assert len(only.alt_paths) == 1  # alternate path recorded


def test_seedgraph_by_kind_and_sort():
    g = SeedGraph()
    g.add(seed(target="GDG Delhi", conf=0.4))
    g.add(seed(kind=SeedKind.SERIES_INSTANCE, target="DevFest Pune", conf=0.9))
    assert g.by_kind() == {"chapter_sibling": 1, "series_instance": 1}
    assert g.all()[0].confidence == 0.9  # sorted desc


def test_budget_and_report_as_dict():
    assert ExpansionBudget().as_dict()["max_depth"] == 3
    from app.ecosystem.models import ExpansionReport

    r = ExpansionReport(seeds_generated=10, seeds_merged=3)
    assert r.as_dict()["unique_seeds"] == 7


# --------------------------------------------------------------------------- templates


def test_templates_present():
    assert "Bangalore" in CITIES and len(CITIES) >= 10
    assert CHAPTER_DISPLAY["gdg"] == "GDG"
    assert any(p[0] == "Build with AI" for p in SPONSOR_PROGRAMS["google"])
    assert any(u[0] == "GDSC" for u in UNIVERSITY_UNITS)


def test_sponsor_key():
    assert sponsor_key("Google Cloud") == "google"
    assert sponsor_key("Microsoft") == "microsoft"
    assert sponsor_key("SomeRandomCo") is None


# --------------------------------------------------------------------------- confidence


def test_confidence_weights_sum_to_one():
    assert abs(sum(CONF_WEIGHTS.values()) - 1.0) < 1e-9


def test_confidence_total_is_weighted_sum():
    cs = ExpansionConfidence().score(
        depth=1,
        relationship_strength=0.9,
        chapter_overlap=1.0,
        technology_overlap=0.8,
        organizer_overlap=0.5,
        recurring=1.0,
    )
    recomputed = sum(cs.components[k] * CONF_WEIGHTS[k] for k in CONF_WEIGHTS)
    assert abs(cs.total - recomputed) < 1e-3
    assert cs.reasons


def test_confidence_graph_distance_falls_with_depth():
    near = ExpansionConfidence().score(depth=1, relationship_strength=0.5)
    far = ExpansionConfidence().score(depth=3, relationship_strength=0.5)
    assert near.components["graph_distance"] > far.components["graph_distance"]


def test_confidence_clips():
    cs = ExpansionConfidence().score(depth=0, relationship_strength=5.0)
    assert cs.components["relationship_strength"] == 1.0


# --------------------------------------------------------------------------- dedup


def test_canonical_target_merges_identity():
    assert canonical_target("GDG Delhi") == canonical_target("Google Developer Group Delhi")


def test_seed_deduplicator():
    dd = SeedDeduplicator()
    seeds = [
        seed(conf=0.4),
        seed(conf=0.8),
        seed(kind=SeedKind.SERIES_INSTANCE, target="DevFest X"),
    ]
    out = dd.dedupe(seeds)
    assert len(out) == 2
    assert SeedDeduplicator.merged_count(seeds) == 1


# --------------------------------------------------------------------------- chapter expander


def test_chapter_expander_generates_siblings():
    seeds = ChapterExpander().expand(
        ctx(profile(name="GDG Bangalore", chapter="gdg", city="Bangalore")), DEFAULT_BUDGET
    )
    targets = {s.target for s in seeds}
    assert "GDG Delhi" in targets and "GDG Bangalore" not in targets  # skips source city
    assert all(s.kind is SeedKind.CHAPTER_SIBLING for s in seeds)
    assert all(s.confidence > 0 for s in seeds)


def test_chapter_expander_no_chapter_empty():
    assert ChapterExpander().expand(ctx(profile(name="Random Org")), DEFAULT_BUDGET) == []


def test_chapter_expander_respects_max_branches():
    seeds = ChapterExpander().expand(
        ctx(profile(name="GDG X", chapter="gdg", city="Bangalore")), ExpansionBudget(max_branches=3)
    )
    assert len(seeds) == 3


def test_chapter_expander_path_and_display():
    seeds = ChapterExpander().expand(
        ctx(profile(name="IEEE MUJ", chapter="ieee", city="Jaipur")), DEFAULT_BUDGET
    )
    s = seeds[0]
    assert s.target.startswith("IEEE ")
    assert s.path.render().startswith("IEEE MUJ --[same_chapter]-->")


# --------------------------------------------------------------------------- series expander


def test_series_expander_instances():
    seeds = SeriesExpander().expand(
        ctx(profile(name="GDG Blr", series=["DevFest"], city="Bangalore")), DEFAULT_BUDGET
    )
    assert any(s.target == "DevFest Delhi" for s in seeds)
    assert all(s.kind is SeedKind.SERIES_INSTANCE for s in seeds)


def test_series_expander_no_series_empty():
    assert SeriesExpander().expand(ctx(profile(name="X")), DEFAULT_BUDGET) == []


def test_series_expander_max_branches():
    seeds = SeriesExpander().expand(
        ctx(profile(name="X", series=["DevFest", "Hacktoberfest"])), ExpansionBudget(max_branches=4)
    )
    assert len(seeds) == 4


# --------------------------------------------------------------------------- sponsor expander


def test_sponsor_expander_known_programs():
    seeds = SponsorExpander().expand(
        ctx(profile(name="GDG", sponsors=["Google"], technologies=["AI", "Cloud"])), DEFAULT_BUDGET
    )
    targets = {s.target for s in seeds}
    assert "Build with AI" in targets
    s = next(s for s in seeds if s.target == "Build with AI")
    assert s.path.depth == 2  # organizer → sponsor → program
    assert s.confidence_breakdown["sponsor_overlap"] == 1.0


def test_sponsor_expander_unknown_sponsor_generic():
    seeds = SponsorExpander().expand(ctx(profile(name="X", sponsors=["Acme Corp"])), DEFAULT_BUDGET)
    assert len(seeds) == 1 and "Acme Corp" in seeds[0].target


def test_sponsor_expander_no_sponsor_empty():
    assert SponsorExpander().expand(ctx(profile(name="X")), DEFAULT_BUDGET) == []


def test_sponsor_expander_recurring_program():
    seeds = SponsorExpander().expand(ctx(profile(name="X", sponsors=["Google"])), DEFAULT_BUDGET)
    bwa = next(s for s in seeds if s.target == "Build with AI")
    assert bwa.confidence_breakdown["recurring_history"] == 1.0


# --------------------------------------------------------------------------- university / venue


def test_university_expander_units():
    seeds = UniversityExpander().expand(
        ctx(profile(name="ACM MUJ", university="IIIT Delhi")), DEFAULT_BUDGET
    )
    assert any("GDSC" in s.target for s in seeds)
    assert all("IIIT Delhi" in s.target for s in seeds)
    assert all(s.kind is SeedKind.UNIVERSITY_UNIT for s in seeds)


def test_university_expander_no_uni_empty():
    assert UniversityExpander().expand(ctx(profile(name="X")), DEFAULT_BUDGET) == []


def test_venue_expander_campus():
    seeds = VenueExpander().expand(
        ctx(profile(name="X", venue="IIT Bombay Campus")), DEFAULT_BUDGET
    )
    assert seeds and all(s.kind is SeedKind.VENUE_UNIT for s in seeds)


def test_venue_expander_noncampus_empty():
    assert VenueExpander().expand(ctx(profile(name="X", venue="Taj Hotel")), DEFAULT_BUDGET) == []


# --------------------------------------------------------------------------- similar organizer


def test_similar_organizer_expander():
    a = profile(name="GDG Bangalore", chapter="gdg", city="Bangalore")
    b = profile(name="GDG Delhi", chapter="gdg", city="Delhi")
    peers = {"org:a": a, "org:b": b}
    seeds = SimilarOrganizerExpander(threshold=0.15).expand(
        ctx(a, source="org:a", peers=peers), DEFAULT_BUDGET
    )
    assert seeds and seeds[0].kind is SeedKind.SIMILAR_ORGANIZER
    assert "GDG Delhi" in {s.target for s in seeds}


def test_similar_organizer_below_threshold_empty():
    a = profile(name="GDG Blr", chapter="gdg", city="Bangalore")
    b = profile(name="IEEE MUJ", chapter="ieee", city="Jaipur")
    peers = {"org:a": a, "org:b": b}
    seeds = SimilarOrganizerExpander(threshold=0.9).expand(
        ctx(a, source="org:a", peers=peers), DEFAULT_BUDGET
    )
    assert seeds == []


def test_similar_organizer_excludes_self():
    a = profile(name="GDG Blr", chapter="gdg", city="Bangalore")
    seeds = SimilarOrganizerExpander(threshold=0.0).expand(
        ctx(a, source="org:a", peers={"org:a": a}), DEFAULT_BUDGET
    )
    assert seeds == []


# --------------------------------------------------------------------------- connected resource


def _graph_with_ecosystem():
    g = OrganizerGraph()
    g.add_node(Node("org:x", NodeType.CHAPTER, "GDG X"))
    g.add_node(Node("gh:1", NodeType.GITHUB_ORG, "github.com/gdgx"))
    g.add_node(Node("sp:google", NodeType.SPONSOR, "Google"))
    g.add_edge(Edge("org:x", "gh:1", RelationType.ANNOUNCES_ON))
    g.add_edge(Edge("sp:google", "org:x", RelationType.SPONSORS))  # reverse direction
    return g


def test_connected_resource_both_directions():
    g = _graph_with_ecosystem()
    seeds = ConnectedResourceExpander().expand(
        ctx(profile(name="GDG X"), graph=g, source="org:x"), DEFAULT_BUDGET
    )
    targets = {s.target for s in seeds}
    assert "github.com/gdgx" in targets and "Google" in targets  # outgoing + incoming
    assert all(s.kind is SeedKind.CONNECTED_RESOURCE for s in seeds)


def test_connected_resource_empty_when_isolated():
    seeds = ConnectedResourceExpander().expand(
        ctx(profile(name="Lonely"), graph=OrganizerGraph(), source="org:lonely"), DEFAULT_BUDGET
    )
    assert seeds == []


def test_connected_resource_relation_strength():
    g = _graph_with_ecosystem()
    seeds = ConnectedResourceExpander().expand(
        ctx(profile(name="GDG X"), graph=g, source="org:x"), DEFAULT_BUDGET
    )
    sponsor_seed = next(s for s in seeds if s.target == "Google")
    ann_seed = next(s for s in seeds if s.target == "github.com/gdgx")
    assert (
        sponsor_seed.confidence_breakdown["relationship_strength"]
        > ann_seed.confidence_breakdown["relationship_strength"]
    )


# --------------------------------------------------------------------------- engine


def _sources():
    return {
        "org:bangalore developer google": profile(
            name="GDG Bangalore",
            chapter="gdg",
            city="Bangalore",
            series=["DevFest"],
            sponsors=["Google"],
            technologies=["AI"],
        ),
        "org:delhi developer google": profile(
            name="GDG Delhi", chapter="gdg", city="Delhi", series=["DevFest"]
        ),
    }


def test_engine_expand_produces_seeds():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=5))
    report = eng.expand(_sources())
    assert report.seeds_generated > 0
    kinds = eng.seeds.by_kind()
    assert "chapter_sibling" in kinds and "sponsor_program" in kinds


def test_engine_dedup_merges_across_sources():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=6))
    report = eng.expand(_sources())
    assert report.seeds_merged > 0  # GDG Bangalore & Delhi generate overlapping city siblings


def test_engine_skips_known_organizer_siblings():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=14))
    eng.expand(_sources())
    sib_targets = {s.target for s in eng.seeds.all() if s.kind is SeedKind.CHAPTER_SIBLING}
    assert "GDG Bangalore" not in sib_targets and "GDG Delhi" not in sib_targets


def test_engine_budget_max_seeds():
    eng = EcosystemExpansionEngine(
        budget=ExpansionBudget(max_seeds=4, max_branches=10, min_confidence=0.1)
    )
    report = eng.expand(_sources())
    assert report.budget_stops >= 1
    assert eng.seeds.as_dict()["count"] <= 4


def test_engine_min_confidence_filter():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(min_confidence=0.95))
    eng.expand(_sources())
    assert eng.seeds.as_dict()["count"] == 0


def test_engine_cooldown_skips_source():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(cooldown_runs=1))
    eng.expand(_sources())
    report2 = eng.expand(_sources())  # within cooldown → skipped
    assert report2.sources_skipped == len(_sources())


def test_engine_incremental_accumulates():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=4))
    eng.expand({"org:a": profile(name="GDG Blr", chapter="gdg", city="Bangalore")})
    first = eng.seeds.as_dict()["count"]
    eng.expand({"org:b": profile(name="PyLadies Delhi", chapter="pyladies", city="Delhi")})
    assert eng.seeds.as_dict()["count"] > first


def test_engine_recommend_limit_and_conf():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=6))
    eng.expand(_sources())
    top = eng.recommend(limit=3)
    assert len(top) == 3
    assert top == sorted(top, key=lambda s: -s.confidence)


def test_engine_relationship_paths_present():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=6))
    eng.expand(_sources())
    assert all(s.path.nodes for s in eng.seeds.all())


def test_engine_expand_from_org_engine():
    from datetime import UTC, datetime

    from app.organizers import OrganizerIntelligenceEngine

    org = OrganizerIntelligenceEngine(clock=lambda: datetime(2026, 7, 16, tzinfo=UTC))
    org.ingest(
        "u", "<h1>GDG Bangalore</h1>Google Developer Group Bangalore. DevFest. AI. Bangalore."
    )
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=5))
    report = eng.expand_from(org)
    assert report.sources_expanded == 1 and eng.seeds.as_dict()["count"] > 0


# --------------------------------------------------------------------------- store


def test_inmemory_seed_store_roundtrip():
    g = SeedGraph()
    g.add(seed())
    store = InMemorySeedStore()
    run(store.save(g))
    assert run(store.load()) is g


def test_sqlite_seed_store_roundtrip():
    g = SeedGraph()
    s = seed(conf=0.7, path=RelationshipPath(nodes=["A", "GDG Delhi"], relations=["same_chapter"]))
    s.alt_paths.append(RelationshipPath(nodes=["B", "GDG Delhi"], relations=["same_series"]))
    g.add(s)
    store = SQLiteSeedStore(":memory:")
    try:
        run(store.save(g))
        loaded = run(store.load())
        assert loaded is not None
        got = loaded.all()[0]
        assert got.target == "GDG Delhi" and got.confidence == 0.7
        assert got.path.relations == ["same_chapter"]
        assert len(got.alt_paths) == 1
        assert run(store.count()) == 1
    finally:
        run(store.close())


def test_engine_persist_and_reload():
    store = SQLiteSeedStore(":memory:")
    try:
        eng = EcosystemExpansionEngine(store=store, budget=ExpansionBudget(max_branches=4))
        eng.expand(_sources())
        run(eng.persist())
        eng2 = EcosystemExpansionEngine(store=store)
        assert run(eng2.load_from_store()) is True
        assert eng2.seeds.as_dict()["count"] >= 4
    finally:
        run(store.close())


# --------------------------------------------------------------------------- additional coverage


def test_seedgraph_as_dict_shape():
    g = SeedGraph()
    g.add(seed())
    d = g.as_dict()
    assert d["count"] == 1 and d["by_kind"]["chapter_sibling"] == 1 and len(d["seeds"]) == 1


def test_relationship_path_zip_mismatch_safe():
    p = RelationshipPath(nodes=["A", "B", "C"], relations=["x"])
    assert "A --[x]--> B" in p.render()


def test_seed_provenance_in_as_dict():
    from app.discovery.ai.models import ExtractionMethod, Provenance

    s = seed()
    s.provenance = Provenance("snip", "reasoned", 0.5, ExtractionMethod.DETERMINISTIC)
    assert s.as_dict()["provenance"] == "reasoned"


def test_templates_more_sponsors_and_cadence():
    from app.ecosystem.templates import SERIES_CADENCE

    assert any(p[0] == "Microsoft Reactor" for p in SPONSOR_PROGRAMS["microsoft"])
    assert any(p[0] == "AWS User Groups" for p in SPONSOR_PROGRAMS["aws"])
    assert SERIES_CADENCE["DevFest"].value == "annual"


def test_chapter_display_covers_families():
    for fam in ("gdg", "gdsc", "ieee", "acm", "pydata", "pyladies", "rust"):
        assert fam in CHAPTER_DISPLAY


def test_confidence_components_reflect_inputs():
    cs = ExpansionConfidence().score(
        depth=2,
        relationship_strength=0.7,
        sponsor_overlap=1.0,
        chapter_overlap=0.0,
        technology_overlap=0.5,
        recurring=1.0,
    )
    assert cs.components["sponsor_overlap"] == 1.0
    assert cs.components["chapter_overlap"] == 0.0
    assert cs.components["recurring_history"] == 1.0
    assert cs.reasons["sponsor_overlap"] == "shared sponsor"


def test_confidence_depth_zero_distance_one():
    cs = ExpansionConfidence().score(depth=0, relationship_strength=0.5)
    assert cs.components["graph_distance"] == 1.0


def test_dedup_empty_and_order():
    assert SeedDeduplicator().dedupe([]) == []
    out = SeedDeduplicator().dedupe([seed(target="B", conf=0.3), seed(target="A", conf=0.9)])
    assert out[0].target == "A"


def test_chapter_recurring_bonus():
    with_series = ChapterExpander().expand(
        ctx(profile(name="GDG X", chapter="gdg", city="Bangalore", series=["DevFest"])),
        DEFAULT_BUDGET,
    )[0]
    without = ChapterExpander().expand(
        ctx(profile(name="GDG X", chapter="gdg", city="Bangalore")), DEFAULT_BUDGET
    )[0]
    assert with_series.confidence > without.confidence


def test_chapter_search_hint_set():
    s = ChapterExpander().expand(
        ctx(profile(name="GDG X", chapter="gdg", city="Bangalore")), DEFAULT_BUDGET
    )[0]
    assert s.search_hint and "tech community" in s.search_hint


def test_chapter_unknown_family_no_display():
    assert (
        ChapterExpander().expand(ctx(profile(name="X", chapter="nonexistent")), DEFAULT_BUDGET)
        == []
    )


def test_series_path_and_hint():
    s = SeriesExpander().expand(
        ctx(profile(name="GDG", series=["DevFest"], city="Bangalore")), DEFAULT_BUDGET
    )[0]
    assert "same_series" in s.path.relations
    assert s.search_hint and "event" in s.search_hint


def test_series_skips_source_city():
    seeds = SeriesExpander().expand(
        ctx(profile(name="X", series=["DevFest"], city="Delhi")), DEFAULT_BUDGET
    )
    assert "DevFest Delhi" not in {s.target for s in seeds}


def test_sponsor_microsoft_programs():
    seeds = SponsorExpander().expand(ctx(profile(name="X", sponsors=["Microsoft"])), DEFAULT_BUDGET)
    assert "Microsoft Reactor" in {s.target for s in seeds}


def test_sponsor_multiple_sponsors():
    seeds = SponsorExpander().expand(
        ctx(profile(name="X", sponsors=["Google", "AWS"])), ExpansionBudget(max_branches=20)
    )
    targets = {s.target for s in seeds}
    assert "Build with AI" in targets and "AWS User Groups" in targets


def test_sponsor_path_relations():
    s = SponsorExpander().expand(ctx(profile(name="X", sponsors=["Google"])), DEFAULT_BUDGET)[0]
    assert s.path.relations == ["sponsors", "runs_program"]


def test_sponsor_tech_overlap():
    s = next(
        x
        for x in SponsorExpander().expand(
            ctx(profile(name="X", sponsors=["Google"], technologies=["AI"])), DEFAULT_BUDGET
        )
        if x.target == "Build with AI"
    )
    assert s.confidence_breakdown["technology_overlap"] > 0


def test_university_all_units_and_hint():
    seeds = UniversityExpander().expand(
        ctx(profile(name="X", university="IIT Delhi")), ExpansionBudget(max_branches=10)
    )
    labels = {s.target.split(",")[0] for s in seeds}
    assert {"ACM Student Chapter", "IEEE Student Branch", "Robotics Club"} <= labels
    assert all(s.path.relations == ["belongs_to", "has_unit"] for s in seeds)


def test_university_max_branches():
    seeds = UniversityExpander().expand(
        ctx(profile(name="X", university="IIT Delhi")), ExpansionBudget(max_branches=3)
    )
    assert len(seeds) == 3


def test_venue_path_via_hosts():
    s = VenueExpander().expand(
        ctx(profile(name="X", venue="NIT Trichy Institute")), DEFAULT_BUDGET
    )[0]
    assert s.path.relations == ["hosts", "has_unit"]


def test_venue_variants():
    for v in ("Some College", "Tech Institute", "IIIT Campus"):
        assert VenueExpander().expand(ctx(profile(name="X", venue=v)), DEFAULT_BUDGET)


def test_similar_ranked_and_path():
    a = profile(name="GDG Blr", chapter="gdg", city="Bangalore", series=["DevFest"])
    b = profile(name="GDG Delhi", chapter="gdg", city="Delhi", series=["DevFest"])
    c = profile(name="IEEE MUJ", chapter="ieee", city="Jaipur")
    peers = {"org:a": a, "org:b": b, "org:c": c}
    seeds = SimilarOrganizerExpander(threshold=0.1).expand(
        ctx(a, source="org:a", peers=peers), DEFAULT_BUDGET
    )
    assert seeds[0].target == "GDG Delhi"
    assert "similar_to" in seeds[0].path.relations


def test_similar_max_branches():
    a = profile(name="GDG Blr", chapter="gdg", city="Bangalore")
    peers = {"org:a": a}
    for i in range(6):
        peers[f"org:{i}"] = profile(name=f"GDG City{i}", chapter="gdg", city=f"City{i}")
    seeds = SimilarOrganizerExpander(threshold=0.0).expand(
        ctx(a, source="org:a", peers=peers), ExpansionBudget(max_branches=3)
    )
    assert len(seeds) == 3


def test_connected_dedups_neighbors():
    g = OrganizerGraph()
    g.add_node(Node("org:x", NodeType.CHAPTER, "GDG X"))
    g.add_node(Node("gh:1", NodeType.GITHUB_ORG, "gh"))
    g.add_edge(Edge("org:x", "gh:1", RelationType.ANNOUNCES_ON))
    g.add_edge(Edge("gh:1", "org:x", RelationType.MEMBER_OF))
    seeds = ConnectedResourceExpander().expand(
        ctx(profile(name="GDG X"), graph=g, source="org:x"), DEFAULT_BUDGET
    )
    assert len([s for s in seeds if s.target == "gh"]) == 1


def test_connected_max_branches():
    g = OrganizerGraph()
    g.add_node(Node("org:x", NodeType.CHAPTER, "X"))
    for i in range(6):
        g.add_node(Node(f"n:{i}", NodeType.WEBSITE, f"site{i}"))
        g.add_edge(Edge("org:x", f"n:{i}", RelationType.ANNOUNCES_ON))
    seeds = ConnectedResourceExpander().expand(
        ctx(profile(name="X"), graph=g, source="org:x"), ExpansionBudget(max_branches=2)
    )
    assert len(seeds) == 2


def test_engine_by_kind_covers_expanders():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=6))
    g = OrganizerGraph()
    g.add_node(Node("org:bangalore developer google", NodeType.CHAPTER, "GDG Bangalore"))
    g.add_node(Node("gh:1", NodeType.GITHUB_ORG, "github"))
    g.add_edge(Edge("org:bangalore developer google", "gh:1", RelationType.ANNOUNCES_ON))
    eng.expand(_sources(), g)
    kinds = set(eng.seeds.by_kind())
    assert {"chapter_sibling", "series_instance", "sponsor_program", "connected_resource"} <= kinds


def test_engine_similar_retained_after_known_filter():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=8))
    eng.expand(_sources())
    assert "similar_organizer" in eng.seeds.by_kind()


def test_engine_report_as_dict_fields():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=4))
    d = eng.expand(_sources()).as_dict()
    assert set(d) >= {
        "sources_expanded",
        "seeds_generated",
        "seeds_merged",
        "unique_seeds",
        "by_kind",
    }


def test_engine_cooldown_zero_does_not_skip():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(cooldown_runs=0, max_branches=3))
    eng.expand(_sources())
    r2 = eng.expand(_sources())
    assert r2.sources_skipped == 0


def test_engine_expand_from_skips_none_profiles():
    class FakeOrg:
        graph = OrganizerGraph()

        def organizer_ids(self):
            return ["a", "b"]

        def profile(self, oid):
            return profile(name="GDG Blr", chapter="gdg", city="Bangalore") if oid == "a" else None

    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=3))
    report = eng.expand_from(FakeOrg())
    assert report.sources_expanded == 1


def test_engine_recommend_min_confidence():
    eng = EcosystemExpansionEngine(budget=ExpansionBudget(max_branches=6, min_confidence=0.1))
    eng.expand(_sources())
    high = eng.recommend(min_confidence=0.6)
    assert all(s.confidence >= 0.6 for s in high)


def test_sqlite_store_empty_load_none():
    store = SQLiteSeedStore(":memory:")
    try:
        assert run(store.load()) is None
        assert run(store.count()) == 0
    finally:
        run(store.close())


def test_inmemory_store_empty_load_none():
    assert run(InMemorySeedStore().load()) is None
