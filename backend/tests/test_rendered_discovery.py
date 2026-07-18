"""Phase 8E — AI Rendered Discovery & Hidden Data Extraction. Fixtures only, NO network/browser."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from app.discovery import InMemoryDiscoveryInbox
from app.discovery.models import DiscoveryStatus, FeedType
from app.discovery.rendered import (
    DiscoveredEndpoint,
    EndpointKind,
    HydrationPayload,
    HydrationSource,
    InMemoryRenderedStore,
    MockAIReasoner,
    RenderedDiscoveryEngine,
    RenderedPage,
    SQLiteRenderedStore,
    classify_endpoint,
    collect_hydration,
    discover_endpoints,
    has_graphql_cache,
    window_globals,
)
from app.discovery.rendered.interfaces import ApiProber, BrowserRenderer, GeminiReasoner
from app.discovery.rendered.prompts import SYSTEM_PROMPT, build_reasoning_prompt

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------- fixtures


def next_data_html(n: int = 250, *, city: str = "Bangalore") -> str:
    events = [
        {"title": f"React India Meetup #{i}", "start_date": f"2026-08-{(i % 28) + 1:02d}"}
        for i in range(n)
    ]
    blob = json.dumps({"props": {"pageProps": {"events": events, "city": city}}, "buildId": "b1"})
    return (
        "<!doctype html><html><head><title>Tech Events India</title></head><body>"
        '<div id="__next"></div>'
        f'<script id="__NEXT_DATA__" type="application/json">{blob}</script>'
        "<script>"
        'const API = "/api/events?city=bangalore";'
        "fetch(API).then(r => r.json());"
        'axios.get("https://api.example.com/v2/events");'
        'fetch("https://example.com/graphql", {method:"POST"});'
        "</script></body></html>"
    )


# ---------------------------------------------------------------------------- hydration


def test_next_data_extraction_counts_events_and_title():
    payloads = collect_hydration(next_data_html(250))
    assert len(payloads) == 1  # __NEXT_DATA__ not double-counted as embedded_json
    p = payloads[0]
    assert p.source == HydrationSource.NEXT_DATA.value
    assert p.event_count == 250
    assert p.sample_title.startswith("React India Meetup #")  # representative, order not guaranteed
    assert "props" in p.top_keys


def test_window_initial_state_and_nuxt_and_apollo():
    html = (
        "<html><body><script>"
        'window.__INITIAL_STATE__ = {"events":[{"name":"VueConf","start_at":"2026-08-02"}]};'
        'window.__NUXT__ = {"data":[{"title":"NuxtMeet","date":"2026-08-03"}]};'
        'window.__APOLLO_STATE__ = {"ROOT_QUERY":{"e":{"title":"GraphConf",'
        '"start_date":"2026-09-01","__typename":"Event"}}};'
        "</script></body></html>"
    )
    by_source = {p.source: p for p in collect_hydration(html)}
    assert by_source["__INITIAL_STATE__"].event_count == 1
    assert by_source["__INITIAL_STATE__"].sample_title == "VueConf"
    assert by_source["__NUXT__"].sample_title == "NuxtMeet"
    assert by_source["__APOLLO_STATE__"].event_count == 1


def test_embedded_json_standalone_is_counted():
    blob = json.dumps({"events": [{"title": "PyData", "start_date": "2026-08-10"}]})
    html = f'<html><body><script type="application/json">{blob}</script></body></html>'
    payloads = collect_hydration(html)
    assert any(
        p.source == HydrationSource.EMBEDDED_JSON.value and p.event_count == 1 for p in payloads
    )


def test_flight_strings_counted_by_signature():
    html = (
        "<html><body><script>"
        'self.__next_f.push([1,"a:[{\\"start_date\\":\\"2026-01-01\\"}]"])'
        "</script></body></html>"
    )
    payloads = collect_hydration(html)
    flight = next(p for p in payloads if p.source == HydrationSource.NEXT_FLIGHT.value)
    assert flight.event_count == 1


def test_webpack_and_vite_detected():
    html = (
        '<html><head><script src="/_next/static/chunks/main-abc.js"></script>'
        '<script type="module" src="/assets/index-x1y2z3.js"></script></head><body></body></html>'
    )
    sources = {p.source for p in collect_hydration(html)}
    assert HydrationSource.WEBPACK.value in sources
    assert HydrationSource.VITE.value in sources


def test_window_globals_and_graphql_cache():
    html = (
        "<script>window.__INITIAL_STATE__={};window.__APOLLO_STATE__={"
        '"ROOT_QUERY":1,"__typename":"X"};</script>'
    )
    assert window_globals(html) == ["__INITIAL_STATE__", "__APOLLO_STATE__"]
    assert has_graphql_cache(html) is True
    assert has_graphql_cache("<html>nothing</html>") is False


def test_external_scripts_are_scanned_for_state():
    script = 'window.__PRELOADED_STATE__ = {"e":[{"title":"K","start_at":"2026-05-05"}]};'
    payloads = collect_hydration("<html><body></body></html>", [script])
    assert any(p.source == "__PRELOADED_STATE__" and p.event_count == 1 for p in payloads)


# ---------------------------------------------------------------------------- endpoints


def test_classify_endpoint_kinds():
    assert classify_endpoint("https://x.com/graphql") is EndpointKind.GRAPHQL
    assert classify_endpoint("https://x.com/cal/e.ics") is EndpointKind.ICS
    assert classify_endpoint("https://calendar.google.com/x") is EndpointKind.CALENDAR
    assert classify_endpoint("https://x.com/feed.rss") is EndpointKind.RSS
    assert classify_endpoint("https://x.com/api/events") is EndpointKind.REST
    assert classify_endpoint("https://x.com/data/events.json") is EndpointKind.JSON
    assert classify_endpoint("https://api.example.com/v2/events") is EndpointKind.REST
    assert classify_endpoint("https://x.com/about") is EndpointKind.UNKNOWN


def test_discover_fetch_axios_xhr_config_graphql():
    html = (
        "<html><body><script>"
        'fetch("https://x.com/api/a.json");'
        'axios.get("https://x.com/api/b");'
        'var r = new XMLHttpRequest(); r.open("GET", "https://x.com/api/c");'
        '{"apiUrl":"https://x.com/api/d"}'
        'fetch("https://x.com/graphql");'
        "</script></body></html>"
    )
    by_url = {e.url: e for e in discover_endpoints(html, [], base="https://x.com/p")}
    assert by_url["https://x.com/api/a.json"].kind is EndpointKind.JSON
    assert by_url["https://x.com/api/a.json"].source == "fetch"
    assert by_url["https://x.com/api/b"].source == "axios"
    assert by_url["https://x.com/api/c"].source == "xhr"
    assert by_url["https://x.com/api/d"].source == "config"
    assert by_url["https://x.com/graphql"].kind is EndpointKind.GRAPHQL


def test_hidden_api_path_literal_and_relative_resolution():
    html = (
        '<html><body><script>const API = "/api/events?city=bangalore";'
        " fetch(API);</script></body></html>"
    )
    eps = discover_endpoints(html, [], base="https://gdg.dev/events")
    urls = {e.url for e in eps}
    assert "https://gdg.dev/api/events?city=bangalore" in urls
    ep = next(e for e in eps if e.url.endswith("bangalore"))
    assert ep.event_relevant is True
    assert ep.kind is EndpointKind.REST


def test_absolute_feed_url_literal_via_variable():
    # `const cal = "https://host/events.ics"; fetch(cal)` — absolute URL behind a variable
    html = (
        '<html><body><script>const cal = "https://pydata.org/events.ics";'
        " fetch(cal);</script></body></html>"
    )
    eps = discover_endpoints(html, [], base="https://pydata.org/calendar")
    ep = next(e for e in eps if e.url == "https://pydata.org/events.ics")
    assert ep.kind is EndpointKind.ICS
    assert ep.event_relevant is True
    # a non-event absolute URL behind a variable is NOT picked up (stays low-noise)
    plain = '<html><body><script>const x = "https://cdn.example.com/app.js";</script></body></html>'
    assert discover_endpoints(plain, [], base="https://x.com/p") == []


def test_event_relevant_endpoints_ranked_first():
    html = (
        "<html><body><script>"
        'fetch("https://x.com/api/config.json");'
        'fetch("https://x.com/api/events.json");'
        "</script></body></html>"
    )
    eps = discover_endpoints(html, [], base="https://x.com/p")
    assert eps[0].event_relevant is True  # events.json sorts before config.json


def test_json_hydration_blob_excluded_from_endpoint_scan():
    # 30 per-event detail/api URLs inside __NEXT_DATA__ must NOT flood the endpoint leads.
    events = [
        {"title": f"E{i}", "start_date": "2026-08-01", "api": f"/api/thing-{i}"} for i in range(30)
    ]
    blob = json.dumps({"props": {"pageProps": {"events": events}}})
    html = (
        f'<html><body><script id="__NEXT_DATA__" type="application/json">{blob}</script>'
        '<script>const API="/api/events"; fetch(API);</script></body></html>'
    )
    eps = discover_endpoints(html, [], base="https://ex.com/e")
    urls = {e.url for e in eps}
    assert "https://ex.com/api/events" in urls
    assert not any("thing-" in u for u in urls)


def test_endpoint_count_is_capped():
    calls = "".join(f'fetch("https://x.com/api/n{i}");' for i in range(60))
    html = f"<html><body><script>{calls}</script></body></html>"
    assert len(discover_endpoints(html, [], base="https://x.com/p")) <= 25


# ---------------------------------------------------------------------------- reasoning


def test_reason_next_data_events_full_verdict():
    hy = [HydrationPayload(HydrationSource.NEXT_DATA.value, 250, "React Meetup")]
    ep = [DiscoveredEndpoint("https://x.com/api/events", EndpointKind.REST, "fetch", True)]
    pc = MockAIReasoner().reason(
        "https://x.com/e", framework="Next.js", hydration=hy, endpoints=ep, html="python react"
    )
    assert pc.is_event_source is True
    assert pc.recommended_provider_type == "next_data"
    assert pc.confidence == 1.0
    assert pc.expected_events == 250
    assert pc.answers["can_be_provider"] is True
    assert pc.missing_fields == ["date", "location", "organizer", "registration_url"]
    assert pc.answers["registration_url"] == "https://x.com/api/events"
    assert "Python" in pc.answers["technology"]
    assert any("event object" in e for e in pc.evidence)
    assert any("full dataset" in e for e in pc.evidence)


def test_reason_event_api_only_is_json_api():
    ep = [DiscoveredEndpoint("https://x.com/api/events", EndpointKind.REST, "fetch", True)]
    pc = MockAIReasoner().reason(
        "https://x.com/e", framework=None, hydration=[], endpoints=ep, html=""
    )
    assert pc.is_event_source is True
    assert pc.recommended_provider_type == "json_api"


def test_reason_graphql_only_not_confident_event():
    ep = [DiscoveredEndpoint("https://x.com/graphql", EndpointKind.GRAPHQL, "fetch", False)]
    pc = MockAIReasoner().reason(
        "https://x.com/e", framework="Next.js", hydration=[], endpoints=ep, html=""
    )
    assert pc.recommended_provider_type == "graphql"
    assert pc.is_event_source is False  # bare graphql endpoint, no event signal


def test_reason_feed_endpoints():
    rss = [DiscoveredEndpoint("https://x.com/feed.rss", EndpointKind.RSS, "html", False)]
    ics = [DiscoveredEndpoint("https://x.com/e.ics", EndpointKind.ICS, "html", True)]
    assert (
        MockAIReasoner()
        .reason("u", framework=None, hydration=[], endpoints=rss, html="")
        .recommended_provider_type
        == "rss"
    )
    assert (
        MockAIReasoner()
        .reason("u", framework=None, hydration=[], endpoints=ics, html="")
        .recommended_provider_type
        == "ics"
    )


def test_reason_hydration_without_events_and_empty():
    hy = [HydrationPayload("__NUXT__", 0, None, ["layout"])]
    pc = MockAIReasoner().reason("u", framework="Nuxt.js", hydration=hy, endpoints=[], html="")
    assert pc.is_event_source is False
    assert pc.recommended_provider_type == "framework"

    empty = MockAIReasoner().reason("u", framework=None, hydration=[], endpoints=[], html="")
    assert empty.recommended_provider_type == "crawl"
    assert empty.confidence == 0.0
    assert empty.missing_fields == []


# ---------------------------------------------------------------------------- engine e2e


def make_engine(inbox=None, store=None, **kw):
    return RenderedDiscoveryEngine(
        inbox or InMemoryDiscoveryInbox(), store=store, clock=lambda: NOW, **kw
    )


def test_engine_next_data_to_inbox_end_to_end():
    inbox = InMemoryDiscoveryInbox()
    report = run(
        make_engine(inbox).discover(
            [RenderedPage("https://example.com/events", next_data_html(250))]
        )
    )
    assert report.pages == 1
    assert report.frameworks == {"Next.js": 1}
    assert report.events_found == 250
    assert report.provider_candidates == 1
    assert report.candidates_inserted == 3  # main next_data + 2 event APIs

    main = run(inbox.get("https://example.com/events"))
    assert main.discovered_by == "rendered"
    assert main.status is DiscoveryStatus.NEW
    assert main.feed_type is FeedType.NEXT_DATA
    assert main.discovery_confidence == 1.0
    assert main.embedded_event_count == 250
    assert main.classification == "next_data"
    assert main.framework == "Next.js"
    assert main.city == "Bangalore"
    assert main.country == "India"


def test_engine_endpoint_candidates_are_json_api():
    inbox = InMemoryDiscoveryInbox()
    run(
        make_engine(inbox).discover(
            [RenderedPage("https://example.com/events", next_data_html(10))]
        )
    )
    api = run(inbox.get("https://api.example.com/v2/events"))
    assert api is not None
    assert api.feed_type is FeedType.JSON_API
    assert api.discovered_by == "rendered"
    assert api.status is DiscoveryStatus.NEW


def test_engine_skips_non_event_pages():
    inbox = InMemoryDiscoveryInbox()
    html = "<html><body><h1>About our company</h1><p>We build things.</p></body></html>"
    report = run(make_engine(inbox).discover([RenderedPage("https://corp.example/about", html)]))
    assert report.provider_candidates == 0
    assert report.skipped == 1
    assert run(inbox.count()) == 0


def test_engine_idempotent_upsert():
    inbox = InMemoryDiscoveryInbox()
    page = RenderedPage("https://example.com/events", next_data_html(10))
    run(make_engine(inbox).discover([page]))
    first = run(inbox.count())
    report2 = run(make_engine(inbox).discover([page]))
    assert run(inbox.count()) == first  # no duplicates
    assert report2.candidates_inserted == 0
    assert report2.candidates_updated == first


def test_engine_min_confidence_floor_filters():
    inbox = InMemoryDiscoveryInbox()
    # an event-API-only page reasons to confidence 0.4; a 0.9 floor holds it back
    html = '<html><body><script>fetch("https://x.com/api/events");</script></body></html>'
    report = run(
        make_engine(inbox, min_confidence=0.9).discover([RenderedPage("https://x.com/p", html)])
    )
    assert report.provider_candidates == 0
    assert report.skipped == 1


def test_engine_persists_rendered_record():
    inbox = InMemoryDiscoveryInbox()
    store = InMemoryRenderedStore()
    run(
        make_engine(inbox, store=store).discover(
            [RenderedPage("https://example.com/events", next_data_html(5))]
        )
    )
    rec = run(store.get("https://example.com/events"))
    assert rec is not None
    assert rec.provider_candidate["recommended_provider_type"] == "next_data"
    assert rec.hydration and rec.endpoints


# ---------------------------------------------------------------------------- store


def test_inmemory_store_roundtrip():
    store = InMemoryRenderedStore()
    from app.discovery.rendered import RenderedRecord

    run(store.save(RenderedRecord("u", {"x": 1}, [{"h": 1}], [{"e": 1}])))
    assert run(store.count()) == 1
    got = run(store.get("u"))
    assert got.provider_candidate == {"x": 1}


def test_sqlite_store_roundtrip():
    store = SQLiteRenderedStore(":memory:")
    from app.discovery.rendered import RenderedRecord

    try:
        run(store.save(RenderedRecord("https://x.com/e", {"t": "next_data"}, [{"h": 1}], [])))
        assert run(store.count()) == 1
        got = run(store.get("https://x.com/e"))
        assert got.provider_candidate == {"t": "next_data"}
        assert got.hydration == [{"h": 1}]
    finally:
        run(store.close())


# ---------------------------------------------------------------------------- interfaces / safety


def test_future_seams_raise_not_implemented():
    for exc_call in (
        lambda: GeminiReasoner().reason("u", framework=None, hydration=[], endpoints=[], html=""),
        lambda: run(BrowserRenderer.render(object(), "u", "<html></html>")),
        lambda: run(ApiProber.probe(object(), None)),
    ):
        raised = False
        try:
            exc_call()
        except NotImplementedError:
            raised = True
        assert raised


def test_prompt_contract_mentions_safety_and_builds():
    assert "NEVER fabricate" in SYSTEM_PROMPT
    assert "unknown" in SYSTEM_PROMPT
    prompt = build_reasoning_prompt(
        "https://x.com/e",
        "Next.js",
        ["__NEXT_DATA__: 250 events"],
        ["/api/events"],
        "<html></html>",
    )
    assert "https://x.com/e" in prompt
    assert "Next.js" in prompt
    assert "/api/events" in prompt
