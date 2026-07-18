"""Phase 6D / D1 — Discovery Engine tests. Deterministic, no network (StaticFetcher + fixtures)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from app.discovery import (
    DiscoveryEngine,
    FeedType,
    InMemoryCrawlCheckpointStore,
    InMemoryDiscoveryInbox,
    Seed,
    SQLiteDiscoveryInbox,
    StaticFetcher,
)
from app.discovery.analysis import analyze_frameworks
from app.discovery.candidates import build_candidate
from app.discovery.crawler import Crawler
from app.discovery.endpoints import find_api_endpoints, find_graphql_endpoints
from app.discovery.feeds import FeedDetection, detect_feeds
from app.discovery.fetch import FetchResult
from app.discovery.frameworks import FrameworkInfo, detect_framework
from app.discovery.hydration import (
    count_event_signatures,
    extract_embedded_json,
    extract_flight_strings,
    extract_next_data,
    extract_window_state,
    find_event_objects,
)
from app.discovery.models import DiscoveryStatus
from app.discovery.robots import RobotsCache, parse_robots
from app.discovery.signals import collect_signals
from app.discovery.urls import normalize_url, registrable_domain, same_scope

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)

RSS = "<rss><channel><item/><item/></channel></rss>"
ATOM = '<feed xmlns="http://www.w3.org/2005/Atom"><entry/></feed>'
ICS2 = "BEGIN:VCALENDAR\nBEGIN:VEVENT\nEND:VEVENT\nBEGIN:VEVENT\nEND:VEVENT\nEND:VCALENDAR"
JSON_FEED = '{"version":"https://jsonfeed.org/version/1","items":[{},{},{}]}'
EVENT_SITEMAP_XML = (
    "<urlset><url><loc>https://x.com/events/a</loc></url>"
    "<url><loc>https://x.com/events/b</loc></url></urlset>"
)
PLAIN_SITEMAP_XML = (
    "<urlset><url><loc>https://x.com/about</loc></url>"
    "<url><loc>https://x.com/team</loc></url><url><loc>https://x.com/pricing</loc></url>"
    "<url><loc>https://x.com/blog</loc></url></urlset>"
)
RICH_PAGE = (
    "<html><head><title>PyData Chennai</title>"
    '<script type="application/ld+json">{"@type":"Event","name":"AI Meetup"}</script>'
    '<script type="application/ld+json">{"@graph":[{"@type":"Event","name":"B"}]}</script>'
    '</head><body itemtype="https://schema.org/Event">'
    '<meta property="og:type" content="event"></body></html>'
)


def run(coro):
    return asyncio.run(coro)


def _r(url, body, ct="text/html", status=200):
    return FetchResult(url=url, status=status, content_type=ct, text=body)


# --------------------------- URL normalization ---------------------------


def test_normalize_url():
    assert normalize_url("https://Example.ORG/Events/") == "https://example.org/Events"
    assert normalize_url("http://x.com:80/a") == "http://x.com/a"
    assert normalize_url("https://x.com/a?utm_source=z&b=2#frag") == "https://x.com/a?b=2"
    assert normalize_url("/events", base="https://x.com/home") == "https://x.com/events"
    assert normalize_url("mailto:a@b.com") is None


def test_registrable_domain_and_scope():
    assert registrable_domain("https://gdg.community.dev/e/1") == "community.dev"
    assert registrable_domain("www.foss.org.in") == "foss.org.in"
    assert same_scope("https://sub.example.com/x", {"example.com"})
    assert not same_scope("https://other.com/x", {"example.com"})


# --------------------------- robots ---------------------------


def test_parse_robots_disallow_allow_delay_sitemap():
    policy = parse_robots(
        "User-agent: *\nDisallow: /private\nAllow: /private/ok\nCrawl-delay: 5\n"
        "Sitemap: https://x.com/sitemap.xml"
    )
    assert policy.allowed("/events") is True
    assert policy.allowed("/private/secret") is False
    assert policy.allowed("/private/ok/page") is True  # longer Allow wins
    assert policy.crawl_delay == 5.0
    assert policy.sitemaps == ["https://x.com/sitemap.xml"]


def test_parse_robots_empty_allows_all():
    assert parse_robots("").allow_all is True
    assert parse_robots("User-agent: *\nDisallow:").allow_all is True


# --------------------------- feed / structured detection ---------------------------


def test_detect_rss_atom_ics_jsonfeed():
    rss = detect_feeds(_r("u", RSS, "application/rss+xml"))[0]
    assert rss == FeedDetection(FeedType.RSS, "u", 2)
    assert detect_feeds(_r("u", ATOM, "application/atom+xml"))[0].feed_type == FeedType.ATOM
    ics = detect_feeds(_r("u", ICS2, "text/calendar"))[0]
    assert ics.feed_type == FeedType.ICS and ics.event_count == 2
    jf = detect_feeds(_r("u", JSON_FEED, "application/feed+json"))[0]
    assert jf == FeedDetection(FeedType.JSON_FEED, "u", 3)


def test_detect_google_calendar_ics():
    url = "https://calendar.google.com/calendar/ical/x/public/basic.ics"
    assert detect_feeds(_r(url, ICS2, "text/calendar"))[0].feed_type == FeedType.GOOGLE_CALENDAR


def test_detect_jsonld_microdata_opengraph():
    detections = detect_feeds(_r("u", RICH_PAGE))
    types = {d.feed_type for d in detections}
    assert FeedType.JSONLD_EVENT in types
    assert FeedType.MICRODATA_EVENT in types
    assert FeedType.OPENGRAPH_EVENT in types
    jsonld = next(d for d in detections if d.feed_type == FeedType.JSONLD_EVENT)
    assert jsonld.event_count == 2 and jsonld.title == "AI Meetup"


def test_detect_event_vs_plain_sitemap():
    ev = detect_feeds(_r("u", EVENT_SITEMAP_XML, "application/xml"))[0]
    plain = detect_feeds(_r("u", PLAIN_SITEMAP_XML, "application/xml"))[0]
    assert ev.feed_type == FeedType.EVENT_SITEMAP
    assert plain.feed_type == FeedType.XML_SITEMAP


# --------------------------- signals ---------------------------


def test_collect_signals_deterministic():
    html = (
        "<html><body>A Python and Kubernetes meetup in Bangalore, India. "
        'Organized by GDG. <a href="/register">Register</a> now for ₹500.'
        '<script type="application/ld+json">{"@type":"Event","name":"X"}</script></body></html>'
    )
    result = _r("https://x.in/e", html)
    detections = detect_feeds(result)
    sig = collect_signals(result, detections, ["https://x.in/events/1", "https://x.in/events/2"])
    assert sig.has_jsonld_event is True
    assert sig.tech_keyword_count >= 2  # Python + Kubernetes
    assert sig.india_reference_count >= 2  # "India" + city + .in
    assert sig.has_organizer is True
    assert sig.has_registration_link is True
    assert sig.has_recurring is True  # 2 event-ish links
    assert sig.structured_count() == 1


# --------------------------- candidate builder + keys ---------------------------


def test_build_candidate_keys_and_aggregates():
    result = _r("https://pydata.org/chennai/event-1", "<html><body>Python AI India</body></html>")
    sig = collect_signals(result, [], [])
    page_det = FeedDetection(FeedType.JSONLD_EVENT, result.url, 1, "AI Day")
    cand = build_candidate(
        result=result, detection=page_det, signals=sig, discovery_path=["seed", result.url], now=NOW
    )
    assert cand.key == "pydata.org#jsonld_event"  # page-level → domain-scoped key
    assert cand.status is DiscoveryStatus.NEW and cand.crawl_timestamp == NOW

    feed_det = FeedDetection(FeedType.RSS, "https://pydata.org/feed.xml", 3)
    feed_cand = build_candidate(
        result=result, detection=feed_det, signals=sig, discovery_path=[], now=NOW
    )
    assert feed_cand.key == "https://pydata.org/feed.xml"  # feed → full URL key


# --------------------------- inbox persistence + dedup ---------------------------


def test_inbox_upsert_dedup_and_status():
    inbox = InMemoryDiscoveryInbox()
    result = _r("https://x.in/e", "<html>Python India</html>")
    det = FeedDetection(FeedType.JSONLD_EVENT, result.url, 1, "T")
    cand = build_candidate(
        result=result,
        detection=det,
        signals=collect_signals(result, [], []),
        discovery_path=[],
        now=NOW,
    )

    assert run(inbox.upsert(cand)) == "inserted"
    assert run(inbox.upsert(cand)) == "updated"  # same key → dedup
    assert run(inbox.count()) == 1
    stored = run(inbox.get(cand.key))
    assert stored.version == 2 and stored.first_seen_at == NOW

    assert run(inbox.set_status(cand.key, DiscoveryStatus.REJECTED, "test")) is True
    assert run(inbox.count(status=DiscoveryStatus.REJECTED)) == 1
    assert run(inbox.count(status=DiscoveryStatus.NEW)) == 0


def test_sqlite_inbox_persists():
    inbox = SQLiteDiscoveryInbox()
    result = _r("https://x.in/e", "<html>Go Rust India</html>")
    det = FeedDetection(FeedType.ICS, "https://x.in/cal.ics", 2)
    cand = build_candidate(
        result=result,
        detection=det,
        signals=collect_signals(result, [det], []),
        discovery_path=["s"],
        now=NOW,
    )
    assert run(inbox.upsert(cand)) == "inserted"
    got = run(inbox.get(cand.key))
    assert got is not None and got.feed_type is FeedType.ICS and got.discovery_path == ["s"]
    assert run(inbox.count()) == 1
    run(inbox.close())


# --------------------------- crawl checkpoint ---------------------------


def test_checkpoint_incremental_skip():
    cp = InMemoryCrawlCheckpointStore()
    run(cp.record("https://x.com/a", "x.com", NOW, 200))
    assert run(cp.was_crawled_since("https://x.com/a", NOW - timedelta(hours=1))) is True
    assert run(cp.was_crawled_since("https://x.com/a", NOW + timedelta(hours=1))) is False
    assert run(cp.was_crawled_since("https://x.com/b", NOW - timedelta(hours=1))) is False
    assert run(cp.visited_count()) == 1


# --------------------------- crawler: robots + scope + dedup ---------------------------


def test_crawler_respects_robots_and_scope():
    home = (
        '<html><a href="/ok">ok</a><a href="/private/secret">no</a>'
        '<a href="https://other.com/x">ext</a></html>'
    )
    responses = {
        "https://example.org/robots.txt": _r(
            "https://example.org/robots.txt", "User-agent: *\nDisallow: /private", "text/plain"
        ),
        "https://example.org/": _r("https://example.org/", home),
        "https://example.org/ok": _r("https://example.org/ok", "<html>ok page</html>"),
    }
    fetcher = StaticFetcher(responses)
    crawler = Crawler(fetcher, RobotsCache(fetcher), max_pages=20, clock=lambda: NOW)

    async def go():
        return [p.url async for p in crawler.crawl("https://example.org/", {"example.org"})]

    urls = run(go())
    assert "https://example.org/ok" in urls
    assert "https://example.org/private/secret" not in urls  # robots-blocked
    assert "https://other.com/x" not in fetcher.calls  # out of scope, filtered at enqueue
    assert crawler.stats.skipped_robots >= 1  # /private/secret enqueued then robots-blocked


# --------------------------- end-to-end engine ---------------------------

_HOME = (
    "<html><head>"
    '<link rel="alternate" type="application/rss+xml" href="/feed.xml">'
    '<link rel="alternate" type="text/calendar" href="/calendar.ics">'
    '</head><body><a href="/events/">Events</a></body></html>'
)
_EVENTS = (
    "<html><head><title>Tech Events</title></head><body>"
    "Python DevOps meetup in Bangalore India, organized by the community. "
    '<a href="/register">Register</a>'
    '<script type="application/ld+json">{"@type":"Event","name":"A"}</script>'
    '<script type="application/ld+json">{"@type":"Event","name":"B"}</script>'
    "</body></html>"
)
_CONF = (
    "<html><body>AI conference India"
    '<script type="application/ld+json">{"@type":"Event","name":"C"}</script></body></html>'
)
_SITEMAP = "<urlset><url><loc>https://example.org/events/conf-2026</loc></url></urlset>"


def _site() -> StaticFetcher:
    return StaticFetcher(
        {
            "https://example.org/robots.txt": _r(
                "https://example.org/robots.txt",
                "Sitemap: https://example.org/sitemap.xml",
                "text/plain",
            ),
            "https://example.org/": _r("https://example.org/", _HOME),
            "https://example.org/events": _r("https://example.org/events", _EVENTS),
            "https://example.org/feed.xml": _r(
                "https://example.org/feed.xml",
                "<rss><channel><item/><item/><item/></channel></rss>",
                "application/rss+xml",
            ),
            "https://example.org/calendar.ics": _r(
                "https://example.org/calendar.ics", ICS2, "text/calendar"
            ),
            "https://example.org/sitemap.xml": _r(
                "https://example.org/sitemap.xml", _SITEMAP, "application/xml"
            ),
            "https://example.org/events/conf-2026": _r(
                "https://example.org/events/conf-2026", _CONF
            ),
        }
    )


def test_engine_end_to_end_discovers_and_dedups():
    inbox = InMemoryDiscoveryInbox()
    checkpoint = InMemoryCrawlCheckpointStore()
    engine = DiscoveryEngine(_site(), inbox, checkpoint=checkpoint, clock=lambda: NOW, max_pages=20)
    report = run(engine.run([Seed("https://example.org/", {"example.org"})]))

    # candidates: JSON-LD (events + conf → one domain#jsonld_event key), RSS, ICS, EVENT_SITEMAP
    assert run(inbox.count()) == 4
    feed_types = {c.feed_type for c in run(inbox.list())}
    assert feed_types == {
        FeedType.JSONLD_EVENT,
        FeedType.RSS,
        FeedType.ICS,
        FeedType.EVENT_SITEMAP,
    }

    jsonld = run(inbox.get("example.org#jsonld_event"))
    assert jsonld.version == 2  # discovered twice (events + conf) → deduped/updated
    assert report.inserted == 4 and report.updated == 1 and report.candidates_found == 5
    assert run(checkpoint.visited_count()) >= 5  # checkpoints persisted
    assert run(inbox.count(status=DiscoveryStatus.NEW)) == 4  # nothing advanced automatically


# =========================================================================
# Phase 6E / D2 — Modern Web Framework Discovery (deterministic, no network, no JS execution)
# =========================================================================

# --- fixtures: one per framework / payload shape ---

NEXT_DATA_EVENTS = (
    "<html><head><title>DevFest</title>"
    '<script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{"events":['
    '{"name":"React India 2026","startDate":"2026-09-01","city":"Bengaluru"},'
    '{"name":"Kubernetes Day","startDate":"2026-10-05","city":"Pune"}'
    "]}}}"
    '</script></head><body><div id="__next"></div></body></html>'
)
NEXT_MARKETING = (  # Next.js present, but the payload has NO event objects
    '<html><head><script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{"hero":{"title":"Welcome"},"nav":["home","about"]}}}'
    '</script></head><body><div id="__next"></div></body></html>'
)
NUXT3_DATA = (
    '<html><body><script id="__NUXT_DATA__" type="application/json">'
    '[{"name":"Nuxt Meetup","date":"2026-06-01"}]'
    "</script></body></html>"
)
NUXT2_FUNC = (  # window.__NUXT__ as an (unparseable) IIFE — fallback signature scan still fires
    "<html><body><script>window.__NUXT__=(function(){return "
    '{"events":[{"name":"Angular Day","start_date":"2026-01-01"}]}}())'
    "</script></body></html>"
)
APOLLO_STATE = (
    '<html><body><div id="root"></div>'
    "<script>window.__APOLLO_STATE__ = "
    '{"Event:1":{"__typename":"Event","name":"GraphQL Summit","startDate":"2026-08-01"}}'
    ";</script></body></html>"
)
INITIAL_STATE = (
    "<html><body><script>window.__INITIAL_STATE__ = "
    '{"events":[{"title":"Vue Conf","start_date":"2026-07-20"}]}'
    "</script></body></html>"
)
EMBEDDED_JSON_EVENTS = (  # no known framework, just a JSON blob with events
    "<html><body>"
    '<script type="application/json">'
    '{"eventList":[{"summary":"Rust Bengaluru","start_at":"2026-05-01"}]}'
    "</script></body></html>"
)
REMIX_HTML = "<html><body><script>window.__remixContext = {};</script></body></html>"
GATSBY_HTML = '<html><body><div id="___gatsby"></div></body></html>'
SVELTEKIT_HTML = "<html><body><script>__sveltekit_x = {}</script></body></html>"
ASTRO_HTML = "<html><body><astro-island></astro-island></body></html>"
VITE_HTML = '<html><body><script type="module" src="/@vite/client"></script></body></html>'
REACT_SPA_HTML = (
    '<html><body><div id="root"></div><script src="/static/js/main.js">react</script></body></html>'
)
API_HTML = (
    '<html><body><div id="root"></div><script>'
    'const a="/api/v1/events";fetch("/api/health");'
    'fetch("https://api.example.com/v2/events");'
    "</script></body></html>"
)
GQL_HTML = '<html><body><script>const uri="/graphql";</script></body></html>'


def _flight_html(*objs) -> str:
    """Build a Next.js App Router RSC page whose Flight pushes carry (escaped) JSON objects."""
    pushes = "".join(
        f"<script>self.__next_f.push([1,{json.dumps(json.dumps(o))}])</script>" for o in objs
    )
    return f'<html><body><div id="__next"></div>{pushes}</body></html>'


# --------------------------- FrameworkDetector ---------------------------


def test_detect_framework_all_families():
    assert detect_framework(NEXT_DATA_EVENTS) == FrameworkInfo("Next.js", "pages-router")
    assert detect_framework(_flight_html({"a": 1})).version == "app-router"
    nuxt3 = detect_framework(NUXT3_DATA)
    assert (nuxt3.name, nuxt3.version) == ("Nuxt", "3")
    nuxt2 = detect_framework(NUXT2_FUNC)
    assert (nuxt2.name, nuxt2.version) == ("Nuxt", "2")
    assert detect_framework(APOLLO_STATE).name == "React (Apollo)"
    assert detect_framework(REMIX_HTML).name == "Remix"
    assert detect_framework(GATSBY_HTML).name == "Gatsby"
    assert detect_framework(SVELTEKIT_HTML).name == "SvelteKit"
    assert detect_framework(ASTRO_HTML).name == "Astro"
    assert detect_framework(VITE_HTML).name == "Vite"
    assert detect_framework(REACT_SPA_HTML).name == "React SPA"
    assert detect_framework("<html><body>plain</body></html>").name is None


# --------------------------- Hydration / NextData / State extractors ---------------------------


def test_extract_next_data_pages_and_nuxt3():
    parsed = extract_next_data(NEXT_DATA_EVENTS)
    assert isinstance(parsed, dict)
    assert extract_next_data(NUXT3_DATA) == [{"name": "Nuxt Meetup", "date": "2026-06-01"}]
    assert extract_next_data("<html>none</html>") is None


def test_extract_window_state_and_unparseable():
    apollo = extract_window_state(APOLLO_STATE, "__APOLLO_STATE__")
    assert apollo is not None and "Event:1" in apollo
    initial = extract_window_state(INITIAL_STATE, "__INITIAL_STATE__")
    assert initial is not None and "events" in initial
    # Nuxt2 function body is not a JSON literal → best-effort parse returns None (documented limit)
    assert extract_window_state(NUXT2_FUNC, "__NUXT__") is None


def test_extract_embedded_json_excludes_ldjson():
    blobs = extract_embedded_json(EMBEDDED_JSON_EVENTS)
    assert len(blobs) == 1 and "eventList" in blobs[0]
    # ld+json is D1's job — the embedded-JSON extractor must NOT pick it up
    assert extract_embedded_json(RICH_PAGE) == []


def test_extract_flight_strings_decodes():
    strings = extract_flight_strings(_flight_html({"a": 1}))
    assert strings and '"a": 1' in strings[0]


def test_find_event_objects_and_signatures():
    obj = {
        "data": {
            "items": [
                {"name": "A", "start_date": "x"},
                {"title": "B", "datetime": "y"},
                {"name": "not-an-event"},  # no date key → ignored
            ],
            "other": {"nope": 1},
        }
    }
    count, title = find_event_objects(obj)
    assert count == 2 and title in {"A", "B"}
    assert count_event_signatures('"startDate": "x" plus "start_at":"y"') == 2
    assert count_event_signatures("nothing here") == 0


# --------------------------- APIEndpointDetector / GraphQLDetector ---------------------------


def test_find_api_endpoints_ranks_event_first():
    eps = find_api_endpoints(API_HTML, "https://example.org/page")
    assert "https://example.org/api/v1/events" in eps
    assert "https://example.org/api/health" in eps
    assert "https://api.example.com/v2/events" in eps
    assert eps[0].endswith("events")  # event-ish endpoint ranked first
    assert len(eps) <= 20


def test_find_graphql_endpoints():
    gql = find_graphql_endpoints(GQL_HTML, "https://example.org/page")
    assert gql == ["https://example.org/graphql"]
    assert find_graphql_endpoints("<html>none</html>", "https://x.org/") == []


# --------------------------- analyze_frameworks (orchestrator) ---------------------------


def test_analyze_nextjs_pages_router():
    a = analyze_frameworks(_r("https://x.in/", NEXT_DATA_EVENTS))
    assert a.framework == "Next.js" and a.framework_version == "pages-router"
    assert a.embedded_event_count == 2 and a.hydration_source == "__NEXT_DATA__"
    assert a.detections[0].feed_type == FeedType.NEXT_DATA
    assert a.signals["has_nextjs"] and a.signals["has_embedded_events"]
    assert a.signals["has_hydration"] and a.signals["has_calendar_schema"]


def test_analyze_app_router_flight():
    html = _flight_html({"startDate": "2026-09-01", "name": "React Day", "city": "Delhi"})
    a = analyze_frameworks(_r("https://rsc.dev/", html))
    assert a.framework_version == "app-router"
    assert a.embedded_event_count >= 1
    assert a.detections[0].feed_type == FeedType.NEXT_FLIGHT


def test_analyze_apollo_and_initial_state():
    apollo = analyze_frameworks(_r("https://a.in/", APOLLO_STATE))
    assert apollo.hydration_source == "__APOLLO_STATE__"
    assert apollo.embedded_event_count == 1
    assert apollo.detections[0].feed_type == FeedType.HYDRATION_STATE

    initial = analyze_frameworks(_r("https://b.in/", INITIAL_STATE))
    assert initial.embedded_event_count == 1
    assert initial.signals["has_calendar_schema"] is True


def test_analyze_embedded_json_without_framework():
    a = analyze_frameworks(_r("https://c.in/", EMBEDDED_JSON_EVENTS))
    assert a.framework is None  # no known framework marker
    assert a.embedded_event_count == 1
    assert a.detections[0].feed_type == FeedType.EMBEDDED_JSON


def test_analyze_nuxt2_function_fallback():
    a = analyze_frameworks(_r("https://d.in/", NUXT2_FUNC))
    assert a.framework == "Nuxt" and a.framework_version == "2"
    assert a.embedded_event_count >= 1  # caught by the raw-HTML signature fallback


def test_analyze_api_and_graphql_endpoints():
    api = analyze_frameworks(_r("https://example.org/", API_HTML))
    assert api.signals["has_api_endpoint"] is True
    assert any(d.feed_type == FeedType.JSON_API for d in api.detections)

    gql = analyze_frameworks(_r("https://example.org/", GQL_HTML))
    assert gql.signals["has_graphql_endpoint"] is True
    assert any(d.feed_type == FeedType.GRAPHQL for d in gql.detections)


def test_analyze_marketing_page_no_false_positive():
    a = analyze_frameworks(_r("https://x.io/", NEXT_MARKETING))
    assert a.framework == "Next.js"  # framework detected...
    assert a.signals["has_nextjs"] is True
    assert a.signals["has_embedded_events"] is False  # ...but no events
    assert a.embedded_event_count == 0
    assert a.detections == []  # → no candidate emitted


# --------------------------- signals + candidate builder (D2 fields) ---------------------------


def test_collect_signals_folds_d2():
    result = _r("https://x.in/", NEXT_DATA_EVENTS)
    a = analyze_frameworks(result)
    sig = collect_signals(result, a.detections, [], a)
    assert sig.has_framework and sig.has_nextjs and sig.has_embedded_events
    assert sig.has_hydration and sig.has_json_array and sig.has_calendar_schema
    assert sig.event_count == 2  # folded from embedded_event_count
    assert sig.structured_count() >= 2  # has_embedded_events + has_hydration both count


def test_build_candidate_d2_fields_and_keys():
    result = _r("https://x.in/", NEXT_DATA_EVENTS)
    a = analyze_frameworks(result)
    sig = collect_signals(result, a.detections, [], a)
    cand = build_candidate(
        result=result,
        detection=a.detections[0],
        signals=sig,
        discovery_path=["seed"],
        now=NOW,
        analysis=a,
    )
    assert cand.key == "x.in#next_data"  # D2 page-level payload → domain-scoped key
    assert cand.framework == "Next.js" and cand.framework_version == "pages-router"
    assert cand.embedded_event_count == 2 and cand.hydration_source == "__NEXT_DATA__"

    # a discovered endpoint keys by its own URL (per-endpoint, not per-domain)
    api = analyze_frameworks(_r("https://example.org/", API_HTML))
    api_det = next(d for d in api.detections if d.feed_type == FeedType.JSON_API)
    api_cand = build_candidate(
        result=_r("https://example.org/", API_HTML),
        detection=api_det,
        signals=collect_signals(_r("https://example.org/", API_HTML), api.detections, [], api),
        discovery_path=[],
        now=NOW,
        analysis=api,
    )
    assert api_cand.key == api_det.url and api_cand.feed_type == FeedType.JSON_API


def test_sqlite_persists_framework_data():
    inbox = SQLiteDiscoveryInbox()
    result = _r("https://x.in/", NEXT_DATA_EVENTS)
    a = analyze_frameworks(result)
    cand = build_candidate(
        result=result,
        detection=a.detections[0],
        signals=collect_signals(result, a.detections, [], a),
        discovery_path=["s"],
        now=NOW,
        analysis=a,
    )
    assert run(inbox.upsert(cand)) == "inserted"
    got = run(inbox.get(cand.key))
    assert got.framework == "Next.js" and got.framework_version == "pages-router"
    assert got.embedded_event_count == 2 and got.hydration_source == "__NEXT_DATA__"
    assert got.api_endpoints == []
    run(inbox.close())


# --------------------------- engine: D2 closes the D1 SPA blind spot ---------------------------

_SPA_HOME = (
    "<html><head><title>DevFest</title>"
    '<script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{"events":['
    '{"name":"DevFest Bangalore 2026","startDate":"2026-11-01","city":"Bengaluru"},'
    '{"name":"DevFest Delhi 2026","startDate":"2026-11-08","city":"Delhi"}'
    "]}}}"
    '</script></head><body><div id="__next"></div></body></html>'
)


def test_engine_discovers_nextjs_spa_events_d1_would_miss():
    # D1 alone finds no event feed here (no JSON-LD / RSS / ICS on the page)…
    d1 = detect_feeds(_r("https://spa.org/", _SPA_HOME))
    assert FeedType.JSONLD_EVENT not in {d.feed_type for d in d1}
    # …but the engine (with D2) recovers the events from __NEXT_DATA__.
    fetcher = StaticFetcher(
        {
            "https://spa.org/robots.txt": _r("https://spa.org/robots.txt", "", "text/plain"),
            "https://spa.org/": _r("https://spa.org/", _SPA_HOME),
        }
    )
    inbox = InMemoryDiscoveryInbox()
    engine = DiscoveryEngine(fetcher, inbox, clock=lambda: NOW, max_pages=10)
    report = run(engine.run([Seed("https://spa.org/", {"spa.org"})]))

    assert report.candidates_found == 1
    cand = run(inbox.get("spa.org#next_data"))
    assert cand is not None
    assert cand.feed_type == FeedType.NEXT_DATA
    assert cand.framework == "Next.js" and cand.embedded_event_count == 2
    assert cand.signals.has_nextjs and cand.signals.has_embedded_events
