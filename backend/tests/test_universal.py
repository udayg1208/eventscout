"""Phase 10B — Universal Event Understanding Engine tests. Fixtures only, NO network/browser/LLM."""

from __future__ import annotations

import asyncio
import json

from app.universal import (
    WEIGHTS,
    AstroExtractor,
    CalendarExtractor,
    DefinitionListExtractor,
    EmbeddedJsonExtractor,
    FaqExtractor,
    FingerprintStore,
    HydrationExtractor,
    JsonLdExtractor,
    MarkdownExtractor,
    MicrodataExtractor,
    NextDataExtractor,
    NuxtExtractor,
    OpenGraphExtractor,
    Page,
    SemanticBlockExtractor,
    TableExtractor,
    UniversalConfidence,
    UniversalEventEngine,
    UniversalValidator,
    fingerprint,
    merge_raw_events,
    normalize,
)
from app.universal.confidence import UniversalConfidence as _UC
from app.universal.models import ExtractionSource, RawEvent
from app.universal.provenance import inferred, known
from app.universal.text_utils import (
    detect_event_type,
    detect_fee,
    detect_location,
    detect_mode,
    detect_technologies,
    find_date,
    find_dates,
    find_registration_url,
    strip_tags,
)


def run(coro):
    return asyncio.run(coro)


def P(html, url="https://x.test/e", ct="text/html") -> Page:
    return Page(url=url, html=html, content_type=ct)


# --------------------------------------------------------------------------- fixtures

JSONLD = (
    "<html><head><title>DevFest</title>"
    '<script type="application/ld+json">{"@type":"Event","name":"DevFest Bangalore 2026",'
    '"startDate":"2026-11-01","endDate":"2026-11-02","description":"AI and cloud",'
    '"location":{"@type":"Place","name":"KTPO","address":{"addressLocality":"Bangalore",'
    '"addressCountry":"India"}},"organizer":{"name":"GDG Bangalore"},'
    '"performer":[{"name":"Ada"},{"name":"Linus"}],'
    '"offers":{"price":"0","url":"https://gdg.dev/reg"}}</script></head>'
    "<body>Python and Kubernetes talks.</body></html>"
)
NEXTDATA = (
    '<html><body><div id="__next"></div><script id="__NEXT_DATA__" type="application/json">'
    + json.dumps(
        {
            "props": {
                "pageProps": {
                    "events": [
                        {"title": "React Meetup", "start_date": "2026-08-01", "city": "Pune"},
                        {"title": "Vue Workshop", "start_date": "2026-08-15", "city": "Delhi"},
                    ]
                }
            }
        }
    )
    + "</script></body></html>"
)
TABLE = (
    "<html><head><title>Schedule</title></head><body><table>"
    "<tr><th>Date</th><th>Event</th><th>Venue</th></tr>"
    "<tr><td>2026-09-01</td><td>Kubernetes Workshop</td><td>Bangalore</td></tr>"
    "<tr><td>2026-09-05</td><td>AI Conference</td><td>Hyderabad</td></tr></table></body></html>"
)
FAQ = (
    "<html><head><title>PyData Bangalore 2026</title></head><body>"
    "<details><summary>When?</summary><p>15 November 2026</p></details>"
    "<details><summary>Where?</summary><p>Bangalore, India</p></details>"
    '<details><summary>How to register?</summary><p><a href="https://pydata.org/reg">RSVP</a></p></details>'
    "<details><summary>Cost?</summary><p>Free</p></details>Python workshop.</body></html>"
)
ICS = (
    "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:FOSDEM DevRoom\nDTSTART:20260201T090000\n"
    "DTEND:20260201T170000\nLOCATION:Brussels\nURL:https://fosdem.org/2026\n"
    "DESCRIPTION:open source conference\nEND:VEVENT\nEND:VCALENDAR"
)
MD = (
    "# Community Events\n\n## PyCon India 2026\n\nJoin us on 2026-10-15 in Bangalore for Python.\n"
    "\n## Rust Meetup\n\nOn 2026-10-20, a Rust workshop in Delhi.\n"
)


# --------------------------------------------------------------------------- text_utils


def test_find_dates_iso_mdy_dmy_numeric():
    assert find_date("on 2026-11-01 join")[0] == "2026-11-01"
    assert find_date("Nov 1, 2026")[0] == "2026-11-01"
    assert find_date("1 November 2026")[0] == "2026-11-01"
    assert find_date("15/11/2026")[0] == "2026-11-15"
    assert find_date("no date here") is None


def test_find_dates_multiple_and_month_year():
    dates = [d[0] for d in find_dates("2026-08-01 and Sep 2026")]
    assert "2026-08-01" in dates and "2026-09" in dates


def test_strip_tags_removes_script_and_tags():
    text = strip_tags("<div>Hi<script>bad()</script> <b>there</b></div>")
    assert "bad()" not in text and "Hi there" in text


def test_find_registration_url_prefers_reg_link():
    html = '<a href="/about">About</a><a href="https://lu.ma/x">Register now</a>'
    url, _ = find_registration_url(html, "https://s.test/p")
    assert url == "https://lu.ma/x"


def test_detect_technologies_mode_type_fee_location():
    assert "Python" in detect_technologies("a python and kubernetes meetup")
    assert detect_mode("this is an online webinar")[0] == "online"
    assert detect_mode("at the venue, in-person")[0] == "offline"
    assert detect_event_type("annual hackathon")[0] == "hackathon"
    assert detect_fee("entry is Free")[0] == "Free"
    assert detect_fee("ticket ₹500")[0].startswith("₹")
    city, _state, country, _ = detect_location("event in Bangalore")
    assert city == "Bangalore" and country == "India"


def test_detect_mode_hybrid():
    assert detect_mode("online stream and in-person venue")[0] == "hybrid"


# --------------------------------------------------------------------------- provenance


def test_known_and_inferred_carry_provenance():
    k = known("v", snippet="s" * 500, reason="r", confidence=1.5)
    assert k.status.value == "extracted" and k.confidence == 1.0
    assert len(k.provenance.source_snippet) <= 200
    i = inferred("India", snippet="Bangalore", reason="r", confidence=0.5)
    assert i.status.value == "inferred"


# --------------------------------------------------------------------------- JSON-LD


def test_jsonld_full_event():
    ev = JsonLdExtractor().extract(P(JSONLD)).events[0]
    assert ev.value("title") == "DevFest Bangalore 2026"
    assert ev.value("start_date") == "2026-11-01"
    assert ev.value("end_date") == "2026-11-02"
    assert ev.value("city") == "Bangalore"
    assert ev.value("country") == "India"
    assert ev.value("venue") == "KTPO"
    assert ev.value("organizer") == "GDG Bangalore"
    assert ev.value("registration_url") == "https://gdg.dev/reg"
    assert ev.value("fee") == "Free"
    assert ev.value("speakers") == ["Ada", "Linus"]
    assert ev.fields["title"].provenance.source_snippet  # provenance present


def test_jsonld_graph_and_multiple():
    html = (
        '<script type="application/ld+json">{"@graph":[{"@type":"Event","name":"A",'
        '"startDate":"2026-01-01"},{"@type":"Event","name":"B","startDate":"2026-02-01"}]}</script>'
    )
    evs = JsonLdExtractor().extract(P(html)).events
    assert {e.value("title") for e in evs} == {"A", "B"}


def test_jsonld_virtual_location_online():
    html = (
        '<script type="application/ld+json">{"@type":"Event","name":"Webinar",'
        '"startDate":"2026-03-01","location":{"@type":"VirtualLocation","name":"Zoom"}}</script>'
    )
    ev = JsonLdExtractor().extract(P(html)).events[0]
    assert ev.value("mode") == "online"


def test_jsonld_no_event_empty():
    html = '<script type="application/ld+json">{"@type":"Organization","name":"X"}</script>'
    assert JsonLdExtractor().extract(P(html)).events == []


def test_jsonld_invalid_json_ignored():
    assert (
        JsonLdExtractor().extract(P('<script type="application/ld+json">{bad</script>')).events
        == []
    )


# --------------------------------------------------------------------------- OpenGraph / Microdata


def test_opengraph_event_and_enrich():
    html = (
        '<meta property="og:title" content="AI Summit Delhi">'
        '<meta property="og:description" content="Python and AI on 2026-05-01">'
        '<meta property="og:site_name" content="AISummit">'
    )
    ev = OpenGraphExtractor().extract(P(html)).events[0]
    assert ev.value("title") == "AI Summit Delhi"
    assert ev.value("organizer") == "AISummit"
    assert ev.value("start_date") == "2026-05-01"
    assert "Python" in ev.value("technologies")


def test_opengraph_no_title_empty():
    assert OpenGraphExtractor().extract(P("<meta name=x content=y>")).events == []


def test_microdata_event():
    html = (
        '<div itemscope itemtype="https://schema.org/Event">'
        '<span itemprop="name">Go Conf</span>'
        '<time itemprop="startDate" datetime="2026-07-01">Jul 1</time>'
        '<span itemprop="location">Mumbai</span></div>'
    )
    ev = MicrodataExtractor().extract(P(html)).events[0]
    assert ev.value("title") == "Go Conf"
    assert ev.value("start_date") == "2026-07-01"
    assert ev.value("venue") == "Mumbai"


def test_microdata_none_empty():
    assert MicrodataExtractor().extract(P("<div>no microdata</div>")).events == []


# --------------------------------------------------------------------------- hydration


def test_nextdata_multiple_events():
    evs = NextDataExtractor().extract(P(NEXTDATA)).events
    assert {e.value("title") for e in evs} == {"React Meetup", "Vue Workshop"}
    assert any(e.value("city") == "Pune" for e in evs)


def test_nuxt_state_event():
    html = (
        '<script>window.__NUXT__ = {"data":[{"events":[{"title":"NuxtMeet",'
        '"start_at":"2026-06-01","city":"Chennai"}]}]}</script>'
    )
    ev = NuxtExtractor().extract(P(html)).events[0]
    assert ev.value("title") == "NuxtMeet" and ev.value("start_date") == "2026-06-01"


def test_astro_island_props():
    props = json.dumps({"events": [{"name": "AstroConf", "startDate": "2026-04-01"}]}).replace(
        '"', "&quot;"
    )
    html = f'<astro-island props="{props}"></astro-island>'
    ev = AstroExtractor().extract(P(html)).events[0]
    assert ev.value("title") == "AstroConf"


def test_hydration_initial_and_apollo_state():
    html = (
        '<script>window.__INITIAL_STATE__ = {"e":[{"name":"ReduxEvt",'
        '"start_date":"2026-05-05"}]}</script>'
        '<script>window.__APOLLO_STATE__ = {"x":{"title":"GqlEvt","startDate":"2026-05-06",'
        '"__typename":"Event"}}</script>'
    )
    titles = {e.value("title") for e in HydrationExtractor().extract(P(html)).events}
    assert "ReduxEvt" in titles and "GqlEvt" in titles


def test_embedded_json_excludes_next_data():
    # __NEXT_DATA__ is application/json but must not be double-counted by the embedded extractor
    assert EmbeddedJsonExtractor().extract(P(NEXTDATA)).events == []


def test_embedded_json_standalone():
    html = (
        '<script type="application/json">{"events":[{"title":"EmbeddedEvt",'
        '"start_date":"2026-09-09"}]}</script>'
    )
    ev = EmbeddedJsonExtractor().extract(P(html)).events[0]
    assert ev.value("title") == "EmbeddedEvt"


# --------------------------------------------------------------------------- textual


def test_markdown_dated_headings():
    evs = MarkdownExtractor().extract(P(MD, ct="text/markdown")).events
    titles = {e.value("title") for e in evs}
    assert "PyCon India 2026" in titles and "Rust Meetup" in titles


def test_markdown_not_markdown_empty():
    assert MarkdownExtractor().extract(P("<html><body><p>hi</p></body></html>")).events == []


def test_table_rows_to_events():
    evs = TableExtractor().extract(P(TABLE)).events
    titles = {e.value("title") for e in evs}
    assert titles == {"Kubernetes Workshop", "AI Conference"}
    ai = next(e for e in evs if e.value("title") == "AI Conference")
    assert ai.value("start_date") == "2026-09-05" and ai.value("venue") == "Hyderabad"


def test_table_without_event_header_empty():
    html = "<table><tr><th>Name</th><th>Age</th></tr><tr><td>Bob</td><td>30</td></tr></table>"
    assert TableExtractor().extract(P(html)).events == []


def test_markdown_table_rows():
    md = "| Date | Event | Venue |\n|------|-------|-------|\n| 2026-08-08 | Docker Day | Pune |\n"
    ev = TableExtractor().extract(P(md, ct="text/markdown")).events[0]
    assert ev.value("title") == "Docker Day" and ev.value("start_date") == "2026-08-08"


def test_definition_list_event():
    html = (
        "<html><head><title>Cloud Meetup</title></head><body><dl>"
        "<dt>When</dt><dd>2026-10-10</dd><dt>Where</dt><dd>Bangalore</dd>"
        "<dt>Cost</dt><dd>Free</dd></dl></body></html>"
    )
    ev = DefinitionListExtractor().extract(P(html)).events[0]
    assert ev.value("title") == "Cloud Meetup"
    assert ev.value("start_date") == "2026-10-10"
    assert ev.value("fee") == "Free"


def test_faq_event():
    ev = FaqExtractor().extract(P(FAQ)).events[0]
    assert ev.value("title") == "PyData Bangalore 2026"
    assert ev.value("start_date") == "2026-11-15"
    assert ev.value("registration_url") == "https://pydata.org/reg"


def test_faq_too_few_pairs_empty():
    html = "<details><summary>When?</summary><p>tomorrow</p></details>"
    assert FaqExtractor().extract(P(html)).events == []


# --------------------------------------------------------------------------- calendar


def test_ics_vevent():
    ev = CalendarExtractor().extract(P(ICS, ct="text/calendar")).events[0]
    assert ev.value("title") == "FOSDEM DevRoom"
    assert ev.value("start_date") == "2026-02-01"
    assert ev.value("end_date") == "2026-02-01"
    assert ev.value("venue") == "Brussels"


def test_ics_multiple_vevents():
    ics = (
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:A\nDTSTART:20260101\nEND:VEVENT\n"
        "BEGIN:VEVENT\nSUMMARY:B\nDTSTART:20260202\nEND:VEVENT\nEND:VCALENDAR"
    )
    assert len(CalendarExtractor().extract(P(ics, ct="text/calendar")).events) == 2


def test_rss_event_item_and_skip_nonevent():
    rss = (
        "<rss><channel><item><title>DevOps Meetup</title>"
        "<description>join on 2026-03-03</description><link>https://x/1</link></item>"
        "<item><title>Random blog</title><description>no event here</description></item>"
        "</channel></rss>"
    )
    evs = CalendarExtractor().extract(P(rss, ct="application/rss+xml")).events
    assert len(evs) == 1 and evs[0].value("title") == "DevOps Meetup"


# --------------------------------------------------------------------------- semantic


def test_semantic_cards_with_dates():
    html = (
        '<div class="event-card"><h3>Cloud Native Day</h3><p>on 2026-11-11 in Bangalore</p></div>'
        '<div class="event-card"><h3>Data Summit</h3><p>2026-11-12, Pune</p></div>'
    )
    titles = {e.value("title") for e in SemanticBlockExtractor().extract(P(html)).events}
    assert titles == {"Cloud Native Day", "Data Summit"}


def test_semantic_block_without_date_skipped():
    html = '<div class="card"><h3>About Us</h3><p>we build things</p></div>'
    assert SemanticBlockExtractor().extract(P(html)).events == []


# --------------------------------------------------------------------------- merge


def test_merge_clusters_by_title():
    a = RawEvent(
        ExtractionSource.JSONLD,
        {
            "title": known("DevFest", snippet="s", reason="r", confidence=0.9),
            "start_date": known("2026-01-01", snippet="s", reason="r", confidence=0.9),
        },
    )
    b = RawEvent(
        ExtractionSource.OPENGRAPH,
        {
            "title": known("devfest", snippet="s", reason="r", confidence=0.5),
            "organizer": known("GDG", snippet="s", reason="r", confidence=0.5),
        },
    )
    merged = merge_raw_events([a, b])
    assert len(merged) == 1
    fields, sources = merged[0]
    assert set(sources) == {"jsonld", "opengraph"}
    assert fields["organizer"].value == "GDG"


def test_merge_best_field_wins():
    strong = known("2026-01-01", snippet="s", reason="r", confidence=0.9)
    weak = inferred("2026-01-01", snippet="s", reason="r", confidence=0.4)
    a = RawEvent(
        ExtractionSource.SEMANTIC,
        {"title": known("X", snippet="s", reason="r", confidence=0.5), "start_date": weak},
    )
    b = RawEvent(
        ExtractionSource.JSONLD,
        {"title": known("X", snippet="s", reason="r", confidence=0.9), "start_date": strong},
    )
    fields, _ = merge_raw_events([a, b])[0]
    assert fields["start_date"].status.value == "extracted"


def test_merge_distinct_titles_separate():
    a = RawEvent(
        ExtractionSource.TABLE, {"title": known("A", snippet="s", reason="r", confidence=0.5)}
    )
    b = RawEvent(
        ExtractionSource.TABLE, {"title": known("B", snippet="s", reason="r", confidence=0.5)}
    )
    assert len(merge_raw_events([a, b])) == 2


# --------------------------------------------------------------------------- normalize


def test_normalize_dedups_tech_and_infers_country():
    f = {
        "title": known("X", snippet="s", reason="r", confidence=0.5),
        "technologies": known(["Python", "python", "AI"], snippet="s", reason="r", confidence=0.5),
        "city": known("Bangalore", snippet="s", reason="r", confidence=0.5),
    }
    out = normalize(f)
    assert out["technologies"].value == sorted({"Python", "python", "AI"})
    assert out["country"].value == "India" and out["country"].status.value == "inferred"


def test_normalize_canonical_event_type():
    f = {"event_type": known("CONF", snippet="s", reason="r", confidence=0.5)}
    assert normalize(f)["event_type"].value == "conference"


# --------------------------------------------------------------------------- validator


def test_validator_accepts_tech_event():
    f = {
        "title": known("Python Meetup", snippet="s", reason="r", confidence=0.8),
        "technologies": known(["Python"], snippet="s", reason="r", confidence=0.8),
    }
    assert UniversalValidator().validate(f).valid


def test_validator_rejects_offtopic_via_context():
    f = {"title": known("Flash Sale Event", snippet="s", reason="r", confidence=0.5)}
    v = UniversalValidator().validate(f, context="Buy now! Add to cart. Deal of the day.")
    assert not v.valid and "shopping" in v.reason


def test_validator_rejects_categories():
    checks = {
        "gambling": "join our casino night jackpot",
        "politics": "campaign rally for the election",
        "jobs": "now hiring, walk-in interview",
        "religion": "prayer meeting and sermon",
    }
    for cat, text in checks.items():
        f = {"title": known("Community Gathering", snippet="s", reason="r", confidence=0.5)}
        v = UniversalValidator().validate(f, context=text)
        assert not v.valid and cat in v.reason


def test_validator_tech_signal_survives_offtopic():
    f = {
        "title": known("DevFest", snippet="s", reason="r", confidence=0.8),
        "technologies": known(["Python"], snippet="s", reason="r", confidence=0.8),
    }
    assert UniversalValidator().validate(f, context="also we are now hiring engineers").valid


def test_validator_requires_title():
    assert not UniversalValidator().validate({}).valid


# --------------------------------------------------------------------------- confidence


def test_confidence_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_confidence_total_is_weighted_sum():
    f = {
        "title": known("X", snippet="s", reason="r", confidence=0.9),
        "start_date": known("2026-01-01", snippet="s", reason="r", confidence=0.9),
        "technologies": known(["Python"], snippet="s", reason="r", confidence=0.9),
        "city": known("Pune", snippet="s", reason="r", confidence=0.9),
    }
    cs = UniversalConfidence().score(f, ["jsonld"])
    recomputed = sum(cs.components[k] * WEIGHTS[k] for k in WEIGHTS)
    assert abs(cs.total - recomputed) < 1e-6
    assert cs.components["structured"] == 1.0  # jsonld is structured
    assert cs.reasons  # every component explained


def test_confidence_structured_beats_semantic():
    f = {
        "title": known("X", snippet="s", reason="r", confidence=0.7),
        "start_date": known("2026-01-01", snippet="s", reason="r", confidence=0.7),
    }
    s = _UC().score(f, ["jsonld"]).total
    w = _UC().score(f, ["semantic"]).total
    assert s > w


# --------------------------------------------------------------------------- fingerprint


def test_fingerprint_stable_and_store():
    assert fingerprint("<a> b </a>") == fingerprint("<a>  b  </a>")  # whitespace-normalized
    store = FingerprintStore()
    fp = fingerprint("<html>x</html>")
    assert not store.unchanged("u", fp)
    store.remember("u", fp)
    assert store.unchanged("u", fp)


# --------------------------------------------------------------------------- engine (integration)


def _engine(**kw):
    return UniversalEventEngine(parallel=False, **kw)


def test_engine_jsonld_end_to_end():
    rep = run(_engine().extract("https://gdg.dev/devfest", JSONLD))
    assert len(rep.events) == 1
    ev = rep.events[0]
    assert ev.title == "DevFest Bangalore 2026"
    assert ev.confidence > 0.5
    assert "jsonld" in ev.sources
    d = ev.as_dict()
    assert d["fields"]["title"]["snippet"] and d["fields"]["start_date"]["value"] == "2026-11-01"


def test_engine_next_data_multi():
    rep = run(_engine().extract("https://x.dev/events", NEXTDATA))
    assert len(rep.events) == 2


def test_engine_table_multi():
    rep = run(_engine().extract("https://c.dev/sched", TABLE))
    assert len(rep.events) == 2


def test_engine_faq_ics_markdown():
    assert len(run(_engine().extract("https://pydata.org", FAQ)).events) == 1
    assert (
        len(run(_engine().extract("https://f.org/e.ics", ICS, content_type="text/calendar")).events)
        == 1
    )
    assert (
        len(
            run(
                _engine().extract("https://r.gh/README.md", MD, content_type="text/markdown")
            ).events
        )
        == 2
    )


def test_engine_merged_provenance():
    html = (
        '<meta property="og:title" content="DevConf India 2026">'
        '<meta property="og:site_name" content="DevConf">'
        '<script type="application/ld+json">{"@type":"Event","name":"DevConf India 2026",'
        '"startDate":"2026-12-01","location":{"name":"Goa"}}</script> Go and Rust.'
    )
    rep = run(_engine().extract("https://devconf.in", html))
    ev = rep.events[0]
    assert set(ev.sources) >= {"jsonld", "opengraph"}
    assert ev.get("organizer") == "DevConf"  # from OG, merged with JSON-LD


def test_engine_rejects_shopping():
    html = (
        '<script type="application/ld+json">{"@type":"Event","name":"Flash Sale",'
        '"startDate":"2026-08-01"}</script> Buy now! Add to cart. Free shipping.'
    )
    rep = run(_engine().extract("https://shop/x", html))
    assert rep.events == [] and rep.rejected >= 1


def test_engine_min_confidence_filter():
    weak = '<div class="card"><h3>Something</h3><p>on 2026-01-01</p></div>'
    strict = run(UniversalEventEngine(parallel=False, min_confidence=0.95).extract("u", weak))
    assert strict.events == []


def test_engine_early_stop_skips_soft_tiers():
    # a confident JSON-LD event stops the pipeline before the textual/semantic tier runs
    rep = run(_engine().extract("https://gdg.dev/devfest", JSONLD))
    assert "semantic" not in rep.extractors_run
    assert "markdown" not in rep.extractors_run
    assert "jsonld" in rep.extractors_run


def test_engine_fingerprint_skips_unchanged():
    store = FingerprintStore()
    eng = UniversalEventEngine(parallel=False, fingerprints=store)
    first = run(eng.extract("https://u", JSONLD))
    second = run(eng.extract("https://u", JSONLD))
    assert not first.skipped_unchanged and second.skipped_unchanged


def test_engine_no_event_page():
    rep = run(
        _engine().extract("https://blog/x", "<html><body><p>just a blog post</p></body></html>")
    )
    assert rep.events == []


def test_engine_sorts_by_confidence():
    rep = run(_engine().extract("https://c.dev/sched", TABLE))
    confs = [e.confidence for e in rep.events]
    assert confs == sorted(confs, reverse=True)


def test_engine_parallel_matches_serial():
    par = run(UniversalEventEngine(parallel=True).extract("u", JSONLD))
    ser = run(UniversalEventEngine(parallel=False).extract("u", JSONLD))
    assert len(par.events) == len(ser.events) == 1
    assert par.events[0].title == ser.events[0].title
