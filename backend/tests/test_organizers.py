"""Phase 10C — Organizer & Community Intelligence tests. Fixtures only, NO network/browser/LLM."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.organizers import (
    Cadence,
    CommunitySimilarity,
    Edge,
    Health,
    InMemoryGraphStore,
    Node,
    NodeType,
    OrganizerConfidence,
    OrganizerExtractor,
    OrganizerGraph,
    OrganizerIntelligenceEngine,
    OrganizerProfile,
    RelationshipDiscoverer,
    RelationType,
    SQLiteGraphStore,
    all_chapters,
    canonical_key,
    canonical_tokens,
    classify_health,
    detect_chapter,
    detect_series,
    detect_university_name,
    detect_university_units,
    dominant_cadence,
    is_same_organizer,
    predict_opportunity,
    resolve_aliases,
)
from app.organizers.confidence import WEIGHTS as CONF_WEIGHTS
from app.organizers.similarity import WEIGHTS as SIM_WEIGHTS
from app.organizers.taxonomy import detect_cadence_word, find_sponsors, is_university
from app.universal.provenance import known

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


def days(n):
    return NOW - timedelta(days=n)


def profile(**kw) -> OrganizerProfile:
    fields = {k: known(v, snippet="s", reason="r", confidence=0.8) for k, v in kw.items()}
    return OrganizerProfile(fields=fields)


GDG = (
    '<html><head><meta property="og:site_name" content="GDG Bangalore">'
    '<link rel="alternate" type="application/rss+xml" href="https://gdgblr.dev/feed.xml"></head>'
    "<body><h1>GDG Bangalore</h1>Google Developer Group Bangalore hosts DevFest and monthly "
    "meetups. Python, Kubernetes, AI. Sponsored by Google. Venue: Bangalore."
    '<a href="https://github.com/gdg-bangalore">GitHub</a>'
    '<a href="https://discord.gg/gdgblr">Discord</a>'
    '<a href="https://linkedin.com/company/gdg-bangalore">LinkedIn</a>'
    '<a href="https://calendar.google.com/calendar/gdgblr">Calendar</a></body></html>'
)


# --------------------------------------------------------------------------- identity


def test_canonical_key_merges_gdg_variants():
    keys = {
        canonical_key(n)
        for n in [
            "GDG Bangalore",
            "Google Developer Group Bangalore",
            "Google Developers Group Bangalore",
        ]
    }
    assert len(keys) == 1


def test_canonical_key_merges_ieee_variants():
    keys = {canonical_key(n) for n in ["IEEE MUJ", "IEEE Student Branch MUJ", "IEEE MUJ SB"]}
    assert len(keys) == 1


def test_canonical_key_distinct_cities():
    assert canonical_key("GDG Bangalore") != canonical_key("GDG Pune")


def test_canonical_tokens_drops_filler():
    assert canonical_tokens("The IEEE Student Branch of MUJ") == frozenset({"ieee", "muj"})


def test_resolve_aliases_groups():
    groups = resolve_aliases(["GDG Bangalore", "Google Developer Group Bangalore", "GDG Pune"])
    assert len(groups) == 2
    assert any(len(v) == 2 for v in groups.values())


def test_is_same_organizer():
    assert is_same_organizer("GDG Bangalore", "Google Developer Group Bangalore")
    assert not is_same_organizer("GDG Bangalore", "GDG Pune")


def test_abbrev_expansion_ug():
    assert canonical_key("AWS UG Bangalore") == canonical_key("AWS User Group Bangalore")


# --------------------------------------------------------------------------- chapters


def test_detect_chapter_families():
    assert detect_chapter("GDG Bangalore")[0] == "gdg"
    assert detect_chapter("GDSC MUJ")[0] == "gdsc"
    assert detect_chapter("IEEE Student Branch")[0] == "ieee"
    assert detect_chapter("PyData Delhi")[0] == "pydata"
    assert detect_chapter("FOSS United Bangalore")[0] == "fossunited"
    assert detect_chapter("random text") is None


def test_detect_chapter_node_types():
    assert detect_chapter("GDSC X")[2] is NodeType.STUDENT_CHAPTER
    assert detect_chapter("IEEE X")[2] is NodeType.PROFESSIONAL_SOCIETY
    assert detect_chapter("GDG X")[2] is NodeType.CHAPTER


def test_all_chapters_multiple():
    fams = {c[0] for c in all_chapters("GDG and PyLadies collaboration")}
    assert "gdg" in fams and "pyladies" in fams


# --------------------------------------------------------------------------- series


def test_detect_series_and_cadence():
    s = {n: c for n, c, _ in detect_series("DevFest 2026 and monthly meetups")}
    assert "DevFest" in s
    assert s["DevFest"] is Cadence.MONTHLY  # explicit "monthly" overrides annual default


def test_detect_series_defaults():
    s = dict((n, c) for n, c, _ in detect_series("Weekly Workshop series"))
    assert s["Weekly Workshop"] is Cadence.WEEKLY


def test_detect_series_none():
    assert detect_series("just a page") == []


def test_dominant_cadence():
    assert dominant_cadence("held monthly", detect_series("monthly meetup")) is Cadence.MONTHLY
    assert dominant_cadence("", []) is Cadence.UNKNOWN


def test_cadence_word():
    assert detect_cadence_word("we meet every week")[0] is Cadence.WEEKLY
    assert detect_cadence_word("no cadence") is None


# --------------------------------------------------------------------------- university


def test_detect_university_name():
    assert detect_university_name("IIT Bombay Techfest")[0] == "IIT Bombay"
    assert detect_university_name("Manipal University Jaipur")[0].startswith("Manipal University")
    assert detect_university_name("just text") is None


def test_detect_university_units():
    labels = {u[0] for u in detect_university_units("Innovation Cell and CS Department")}
    assert "innovation cell" in labels and "department" in labels


def test_is_university():
    assert is_university("IIT Delhi") and not is_university("GDG Bangalore")


# --------------------------------------------------------------------------- taxonomy


def test_find_sponsors():
    s = find_sponsors("Sponsored by Google. Powered by AWS.")
    names = {x[0] for x in s}
    assert "Google" in names and "AWS" in names


# --------------------------------------------------------------------------- extract


def test_extract_gdg_full_profile():
    p = OrganizerExtractor().extract("https://gdgblr.dev/", GDG)
    assert p.get("name") == "GDG Bangalore"
    assert p.get("chapter") == "gdg"
    assert p.get("community") == "Google Developer Group"
    assert "DevFest" in p.get("series")
    assert p.get("city") == "Bangalore"
    assert p.get("venue") == "Bangalore"
    assert "Python" in p.get("technologies")
    assert "google" in [s.lower() for s in p.get("sponsors")]
    social = p.get("social_pages")
    assert set(social) >= {"github", "discord", "linkedin"}
    assert p.get("calendars") and p.get("feeds")
    assert p.node_type is NodeType.CHAPTER


def test_extract_name_from_hint():
    p = OrganizerExtractor().extract("u", "<html></html>", hint_name="PyLadies Delhi")
    assert p.get("name") == "PyLadies Delhi" and p.get("chapter") == "pyladies"


def test_extract_university_club():
    p = OrganizerExtractor().extract("u", "<h1>ACM MUJ</h1> IEEE at Manipal University Jaipur")
    assert p.get("university")
    assert p.node_type in (NodeType.PROFESSIONAL_SOCIETY, NodeType.UNIVERSITY_CLUB)


def test_extract_jsonld_parent():
    html = '<h1>GDG Blr</h1><script>{"parentOrganization":{"name":"Google"}}</script>'
    p = OrganizerExtractor().extract("u", html)
    assert p.get("parent_org") == "Google"


def test_extract_provenance_present():
    p = OrganizerExtractor().extract("https://gdgblr.dev/", GDG)
    assert p.fields["name"].provenance.source_snippet
    assert p.fields["chapter"].provenance.reason == "chapter family"


# --------------------------------------------------------------------------- graph model


def test_graph_add_node_merges():
    g = OrganizerGraph()
    g.add_node(Node("a", NodeType.ORGANIZATION, "A", aliases={"A"}))
    g.add_node(Node("a", NodeType.ORGANIZATION, "Alpha", aliases={"Alpha"}))
    assert len(g.nodes) == 1
    assert g.nodes["a"].aliases == {"A", "Alpha"}
    assert g.nodes["a"].label == "Alpha"  # richest label


def test_graph_add_edge_dedups():
    g = OrganizerGraph()
    g.add_edge(Edge("a", "b", RelationType.ORGANIZES))
    g.add_edge(Edge("a", "b", RelationType.ORGANIZES))
    assert len(g.edges) == 1


def test_graph_merge_nodes_reassigns_edges():
    g = OrganizerGraph()
    for i in ("a", "b", "c"):
        g.add_node(Node(i, NodeType.ORGANIZATION, i))
    g.add_edge(Edge("b", "c", RelationType.ORGANIZES))
    g.merge_nodes("a", "b")
    assert "b" not in g.nodes
    assert any(e.source == "a" and e.target == "c" for e in g.edges.values())


def test_graph_neighbors_and_subgraph():
    g = OrganizerGraph()
    g.add_node(Node("o", NodeType.ORGANIZATION, "O"))
    g.add_node(Node("s", NodeType.CONFERENCE_SERIES, "S"))
    g.add_edge(Edge("o", "s", RelationType.ORGANIZES))
    assert [n.id for n in g.neighbors("o")] == ["s"]
    assert len(g.series_view().nodes) == 2


def test_graph_as_dict_counts():
    g = OrganizerGraph()
    g.add_node(Node("o", NodeType.ORGANIZATION, "O"))
    d = g.as_dict()
    assert d["counts"]["nodes"] == 1 and d["counts"]["by_type"]["organization"] == 1


# --------------------------------------------------------------------------- similarity


def test_similarity_same_organizer():
    a = profile(name="GDG Bangalore")
    b = profile(name="Google Developer Group Bangalore")
    s = CommunitySimilarity().score(a, b)
    assert s.components["same_organizer"] == 1.0 and s.total > 0.25


def test_similarity_same_chapter_diff_city():
    a = profile(name="GDG Bangalore", chapter="gdg", city="Bangalore")
    b = profile(name="GDG Pune", chapter="gdg", city="Pune")
    s = CommunitySimilarity().score(a, b)
    assert s.components["same_chapter"] == 1.0 and s.components["same_city"] == 0.0


def test_similarity_weights_sum_and_total():
    assert abs(sum(SIM_WEIGHTS.values()) - 1.0) < 1e-9
    a = profile(name="X", chapter="gdg", city="Delhi", series=["DevFest"])
    b = profile(name="Y", chapter="gdg", city="Delhi", series=["DevFest"])
    s = CommunitySimilarity().score(a, b)
    assert abs(s.total - sum(s.components[k] * SIM_WEIGHTS[k] for k in SIM_WEIGHTS)) < 1e-6


def test_similarity_different():
    a = profile(name="GDG Blr", chapter="gdg", city="Bangalore")
    b = profile(name="IEEE MUJ", chapter="ieee", city="Jaipur")
    assert CommunitySimilarity().score(a, b).total < 0.2


# --------------------------------------------------------------------------- confidence


def test_confidence_weights_sum():
    assert abs(sum(CONF_WEIGHTS.values()) - 1.0) < 1e-9


def test_confidence_total_is_weighted_sum():
    p = profile(
        name="GDG",
        series=["DevFest"],
        domains=["gdg.dev"],
        social_pages={"github": "x", "discord": "y"},
        calendars=["c"],
        chapter="gdg",
    )
    cs = OrganizerConfidence().score(p, event_count=3)
    assert abs(cs.total - sum(cs.components[k] * CONF_WEIGHTS[k] for k in CONF_WEIGHTS)) < 1e-3
    assert cs.components["recurring"] == 1.0 and cs.reasons


def test_confidence_low_for_bare_name():
    cs = OrganizerConfidence().score(profile(name="Someone"))
    assert cs.total < 0.3


# --------------------------------------------------------------------------- health


def test_health_new_no_events():
    assert classify_health([], Cadence.MONTHLY, NOW) is Health.NEW


def test_health_active_recent():
    assert classify_health([days(60), days(30), days(5)], Cadence.MONTHLY, NOW) is Health.ACTIVE


def test_health_future_event_active():
    assert classify_health([NOW + timedelta(days=10)], Cadence.MONTHLY, NOW) is Health.ACTIVE


def test_health_dormant():
    # ~70d since last, monthly cadence → past active (46d) but within 3× period (93d)
    assert classify_health([days(130), days(70)], Cadence.MONTHLY, NOW) is Health.DORMANT


def test_health_inactive():
    assert classify_health([days(800), days(700)], Cadence.MONTHLY, NOW) is Health.INACTIVE


def test_health_seasonal_annual():
    # ~600d since last, annual cadence → past active (549d) but within 2× period (732d)
    assert classify_health([days(1000), days(600)], Cadence.ANNUAL, NOW) is Health.SEASONAL


def test_health_single_event_new():
    assert classify_health([days(10)], Cadence.MONTHLY, NOW) is Health.NEW


# --------------------------------------------------------------------------- prediction


def test_predict_none_without_history():
    assert predict_opportunity([], Cadence.MONTHLY, NOW).probability == "none"


def test_predict_high_when_due():
    p = predict_opportunity([days(65), days(34)], Cadence.MONTHLY, NOW)
    assert p.probability == "high" and "upcoming announcement" in p.reason
    assert p.expected_next is not None


def test_predict_low_when_recent():
    assert predict_opportunity([days(5)], Cadence.MONTHLY, NOW).probability == "low"


def test_predict_medium_when_overdue():
    assert predict_opportunity([days(200)], Cadence.MONTHLY, NOW).probability == "medium"


# --------------------------------------------------------------------------- relationships


def test_relationship_expansion():
    g = OrganizerGraph()
    g.add_node(Node("org:x", NodeType.CHAPTER, "GDG X"))
    p = profile(
        parent_org="Google Developer Group",
        chapter="gdg",
        series=["DevFest"],
        sponsors=["Google"],
        calendars=["https://c/x.ics"],
        feeds=["https://f/rss"],
        domains=["gdgx.dev"],
        social_pages={"discord": "https://discord.gg/x"},
    )
    RelationshipDiscoverer().expand(g, "org:x", p)
    rels = {e.relation for e in g.edges.values()}
    assert RelationType.CHAPTER_OF in rels
    assert RelationType.ORGANIZES in rels
    assert RelationType.SPONSORS in rels
    assert RelationType.USES_CALENDAR in rels
    assert RelationType.USES_FEED in rels
    assert RelationType.ANNOUNCES_ON in rels
    assert RelationType.RECURRING in rels


# --------------------------------------------------------------------------- engine


def _engine():
    return OrganizerIntelligenceEngine(clock=lambda: NOW)


def test_engine_ingest_and_alias_merge():
    eng = _engine()
    a = eng.ingest("https://gdgblr.dev/", GDG)
    b = eng.ingest("u", "<h1>Google Developers Group Bangalore</h1> DevFest in Bangalore.")
    assert a == b  # aliases resolved to one node
    assert len(eng.organizer_ids()) == 1


def test_engine_ecosystem_expanded():
    eng = _engine()
    eng.ingest("https://gdgblr.dev/", GDG)
    types = eng.graph.as_dict()["counts"]["by_type"]
    assert types.get("conference_series", 0) >= 1
    assert types.get("github_org", 0) == 1 and types.get("calendar", 0) == 1
    assert any(e.relation is RelationType.CHAPTER_OF for e in eng.graph.edges.values())


def test_engine_confidence_health_prediction():
    eng = _engine()
    gid = eng.ingest("https://gdgblr.dev/", GDG)
    eng.record_events(gid, [days(65), days(34)])
    assert eng.confidence(gid).total > 0.5
    assert eng.health(gid) is Health.ACTIVE
    assert eng.predict(gid).probability == "high"


def test_engine_similarity_and_link():
    eng = _engine()
    eng.ingest("https://gdgblr.dev/", GDG)
    eng.ingest("u", "<h1>GDG Pune</h1> Google Developer Group Pune. DevFest. Pune.")
    ids = eng.organizer_ids()
    s = eng.similarity(ids[0], ids[1])
    assert s.components["same_chapter"] == 1.0
    eng.link_similar(threshold=0.2)
    assert any(e.relation is RelationType.SAME_COMMUNITY for e in eng.graph.edges.values())


def test_engine_ingest_organizer_helper():
    eng = _engine()
    oid = eng.ingest_organizer("IEEE MUJ", text="IEEE Student Branch. Robotics.")
    assert oid == "org:ieee muj"
    assert eng.profile(oid).get("chapter") == "ieee"


def test_engine_profile_merge_incremental():
    eng = _engine()
    eng.ingest("u", "<h1>GDG Bangalore</h1>")
    eng.ingest("https://gdgblr.dev/", GDG)  # richer page merges in
    p = eng.profile("org:bangalore developer google")
    assert p.get("series") and p.get("social_pages")


# --------------------------------------------------------------------------- store


def test_inmemory_store_roundtrip():
    g = OrganizerGraph()
    g.add_node(Node("o", NodeType.ORGANIZATION, "O", aliases={"O"}))
    store = InMemoryGraphStore()
    run(store.save(g))
    assert run(store.load()) is g


def test_sqlite_store_roundtrip():
    g = OrganizerGraph()
    g.add_node(
        Node("org:x", NodeType.CHAPTER, "GDG X", attributes={"chapter": "gdg"}, aliases={"GDG X"})
    )
    g.add_node(Node("series:d", NodeType.CONFERENCE_SERIES, "DevFest"))
    g.add_edge(Edge("org:x", "series:d", RelationType.ORGANIZES, "runs"))
    store = SQLiteGraphStore(":memory:")
    try:
        run(store.save(g))
        loaded = run(store.load())
        assert loaded is not None
        assert loaded.nodes["org:x"].type is NodeType.CHAPTER
        assert loaded.nodes["org:x"].attributes["chapter"] == "gdg"
        assert ("org:x", "organizes", "series:d") in loaded.edges
        assert run(store.count()) == (2, 1)
    finally:
        run(store.close())


def test_engine_persist_and_reload():
    store = SQLiteGraphStore(":memory:")
    try:
        eng = OrganizerIntelligenceEngine(store=store, clock=lambda: NOW)
        eng.ingest("https://gdgblr.dev/", GDG)
        run(eng.persist())
        eng2 = OrganizerIntelligenceEngine(store=store, clock=lambda: NOW)
        assert run(eng2.load_from_store()) is True
        assert len(eng2.graph.nodes) >= 5
    finally:
        run(store.close())


# --------------------------------------------------------------------------- additional coverage


def test_identity_more_abbrevs():
    assert canonical_key("GDSC MUJ") == canonical_key("Google Developer Student Club MUJ")
    assert canonical_key("TFUG Delhi") == canonical_key("TensorFlow User Group Delhi")
    assert canonical_key("") == ""


def test_identity_threshold_partial():
    assert is_same_organizer("Rust Delhi Community", "Delhi Rust")
    assert not is_same_organizer("Rust Delhi", "Python Mumbai")


def test_chapter_more_families():
    for text, fam in [
        ("Mozilla Campus", "mozilla"),
        ("AWS User Group Pune", "aws_ug"),
        ("Kubernetes Community Days", "kubernetes"),
        ("Rust Bangalore", "rust"),
        ("PyLadies", "pyladies"),
        ("ACM Chapter", "acm"),
    ]:
        assert detect_chapter(text)[0] == fam


def test_series_more_brands():
    for text, name in [
        ("Build with AI Delhi", "Build with AI"),
        ("Hacktoberfest 2026", "Hacktoberfest"),
        ("PyCon India", "PyCon"),
        ("Cloud Community Day", "Cloud Community Day"),
    ]:
        assert any(s[0] == name for s in detect_series(text))


def test_series_multiple():
    names = {s[0] for s in detect_series("DevFest and Hacktoberfest and Study Jam")}
    assert {"DevFest", "Hacktoberfest", "Study Jam"} <= names


def test_university_units_student_chapter_and_coe():
    labels = {u[0] for u in detect_university_units("Student Branch and Center of Excellence")}
    assert "student chapter" in labels and "center of excellence" in labels


def test_extract_notion_and_telegram():
    html = (
        '<h1>PyData Delhi</h1><a href="https://pydata.notion.site/wiki">wiki</a>'
        '<a href="https://t.me/pydatadelhi">tg</a>'
    )
    social = OrganizerExtractor().extract("https://pydata.dev/", html).get("social_pages")
    assert "notion" in social and "telegram" in social


def test_extract_domains_include_base_and_external():
    html = '<h1>GDG X</h1><a href="https://external.org/x">ext</a>'
    doms = OrganizerExtractor().extract("https://gdgx.dev/", html).get("domains")
    assert "gdgx.dev" in doms and "external.org" in doms


def test_extract_no_name_returns_empty_name():
    p = OrganizerExtractor().extract("https://x.dev/", "<html><body>nothing</body></html>")
    assert p.get("name") is None


def test_graph_nodes_and_edges_of():
    g = OrganizerGraph()
    g.add_node(Node("o", NodeType.ORGANIZATION, "O"))
    g.add_node(Node("s", NodeType.SPONSOR, "S"))
    g.add_edge(Edge("s", "o", RelationType.SPONSORS))
    assert len(g.nodes_of(NodeType.SPONSOR)) == 1
    assert len(g.edges_of(RelationType.SPONSORS)) == 1


def test_graph_community_view_has_chapter_edges():
    g = OrganizerGraph()
    g.add_node(Node("c", NodeType.CHAPTER, "GDG Blr"))
    g.add_node(Node("p", NodeType.ORGANIZATION, "GDG"))
    g.add_edge(Edge("c", "p", RelationType.CHAPTER_OF))
    view = g.community_view()
    assert len(view.nodes) == 2 and len(view.edges) == 1


def test_similarity_university_and_sponsors():
    a = profile(name="A", university="IIT Bombay", sponsors=["Google", "AWS"])
    b = profile(name="B", university="IIT Bombay", sponsors=["Google"])
    s = CommunitySimilarity().score(a, b)
    assert s.components["same_university"] == 1.0
    assert 0 < s.components["same_sponsors"] < 1.0


def test_confidence_calendars_and_feeds_components():
    p = profile(name="X", calendars=["c"], feeds=["f"])
    cs = OrganizerConfidence().score(p)
    assert cs.components["calendars"] == 1.0 and cs.components["feeds"] == 1.0


def test_health_unknown_cadence_uses_median_gap():
    # ~30-day gaps → period ~30 → 20d since last is active
    assert classify_health([days(80), days(50), days(20)], Cadence.UNKNOWN, NOW) is Health.ACTIVE


def test_prediction_as_dict():
    d = predict_opportunity([days(65), days(34)], Cadence.MONTHLY, NOW).as_dict()
    assert d["probability"] == "high" and d["expected_next"]


def test_relationship_university_department_nodes():
    g = OrganizerGraph()
    g.add_node(Node("org:x", NodeType.UNIVERSITY_CLUB, "ACM MUJ"))
    p = profile(university="Manipal University Jaipur", department="CS Department")
    RelationshipDiscoverer().expand(g, "org:x", p)
    types = {n.type for n in g.nodes.values()}
    assert NodeType.UNIVERSITY in types and NodeType.DEPARTMENT in types


def test_engine_link_similar_series_edge():
    eng = _engine()
    eng.ingest("u", "<h1>GDG Delhi</h1> Google Developer Group Delhi. DevFest. Delhi.")
    eng.ingest("u", "<h1>GDG Mumbai</h1> Google Developer Group Mumbai. DevFest. Mumbai.")
    eng.link_similar(threshold=0.15)
    rels = {e.relation for e in eng.graph.edges.values()}
    assert RelationType.SAME_SERIES in rels


def test_engine_series_graph_view():
    eng = _engine()
    eng.ingest("https://gdgblr.dev/", GDG)
    assert len(eng.series_graph().nodes) >= 1


def test_engine_health_inactive_old():
    eng = _engine()
    gid = eng.ingest_organizer("Old Group", text="Python meetup")
    eng.record_events(gid, [days(900)])
    assert eng.health(gid) is Health.INACTIVE
