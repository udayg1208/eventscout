"""Endpoint & API discovery (Phase 8E) — the hidden APIs a SPA calls.

Instead of crawling HTML forever, find the endpoint the page fetches its events from. Reuses D2's
`find_api_endpoints` / `find_graphql_endpoints` over the HTML and adds extraction of `fetch()` /
`axios()` / `XMLHttpRequest.open()` / GraphQL calls inside JS, plus config URLs. Classifies each as
REST / GraphQL / JSON / RSS / ICS / calendar. URLs are recorded as future providers — **never
called** (no network, no probing).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.discovery.endpoints import find_api_endpoints, find_graphql_endpoints
from app.discovery.rendered.models import DiscoveredEndpoint, EndpointKind
from app.discovery.urls import normalize_url

_FETCH = re.compile(r"""fetch\(\s*[`'"]([^`'"]+)[`'"]""")
_AXIOS = re.compile(r"""axios(?:\.(?:get|post|put|request))?\(\s*[`'"]([^`'"]+)[`'"]""")
_XHR = re.compile(r"""\.open\(\s*[`'"](?:GET|POST)[`'"]\s*,\s*[`'"]([^`'"]+)[`'"]""", re.IGNORECASE)
_CONFIG = re.compile(
    r"""["'](?:apiUrl|apiBase|endpoint|baseURL|api_url)["']\s*:\s*["']([^"']+)["']""", re.I
)
_GQL_REF = re.compile(r"""[`'"]([^`'"]*/(?:graphql|gql)[^`'"]*)[`'"]""", re.IGNORECASE)
# a quoted absolute-path literal that names an API/events route — the hidden endpoint a SPA fetches
# (e.g. `const API = "/api/events?city=bangalore"`). Scanned over executable JS only (see below).
_PATH_LIT = re.compile(
    r"""[`'"](/(?:api|v\d+)/[^`'"\s]*|/[^`'"\s]*events?[^`'"\s]*)[`'"]""", re.IGNORECASE
)
# a quoted ABSOLUTE url that clearly names an event API or a feed/calendar — catches the common
# `const cal = "https://host/events.ics"; fetch(cal)` variable-indirection pattern. Deliberately
# narrow (must contain /api/ | /events | .ics | .rss | /feed | /graphql) to stay low-noise.
_URL_LIT = re.compile(
    r"""[`'"](https?://[^`'"\s]*(?:/api/|/events?\b|\.ics\b|\.rss\b|/feed\b|/(?:graphql|gql)\b)"""
    r"""[^`'"\s]*)[`'"]""",
    re.IGNORECASE,
)
# inline <script> bodies that are NOT JSON (skip application/json + ld+json hydration blobs)
_EXEC_SCRIPT = re.compile(
    r"<script(?![^>]*application/(?:ld\+)?json)[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL
)
# JSON hydration blobs to remove before endpoint scanning — a 250-event __NEXT_DATA__ payload
# carries per-event detail URLs that would otherwise flood (and cap out) the real endpoint leads.
_JSON_SCRIPT = re.compile(
    r"<script[^>]*application/(?:ld\+)?json[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL
)

_KIND = [
    (re.compile(r"/(graphql|gql)\b", re.I), EndpointKind.GRAPHQL),
    (re.compile(r"\.ics(\b|$)", re.I), EndpointKind.ICS),
    (re.compile(r"calendar\.google\.com|/calendar", re.I), EndpointKind.CALENDAR),
    (re.compile(r"/(feed|rss|atom)\b|\.(xml|rss)\b", re.I), EndpointKind.RSS),
    (re.compile(r"/api/|\.json\b", re.I), EndpointKind.REST),
    # a REST-ish data path even without a literal /api/ segment (e.g. api.host/v2/events)
    (re.compile(r"/(?:v\d+/)?events?(?:/|\?|\b|$)|^https?://api\.", re.I), EndpointKind.REST),
]
_EVENTISH = re.compile(r"event", re.IGNORECASE)


def classify_endpoint(url: str) -> EndpointKind:
    for pattern, kind in _KIND:
        if pattern.search(url):
            return (
                EndpointKind.JSON if kind is EndpointKind.REST and ".json" in url.lower() else kind
            )
    return EndpointKind.UNKNOWN


def _resolve(raw: str, base: str) -> str | None:
    if raw.startswith(("http://", "https://")):
        return normalize_url(raw)
    if raw.startswith("/"):
        origin = "{0.scheme}://{0.netloc}".format(urlsplit(base))
        return normalize_url(origin + raw)
    return None  # skip templated / relative-fragment URLs we can't resolve deterministically


def discover_endpoints(
    html: str, scripts: list[str] | None = None, *, base: str
) -> list[DiscoveredEndpoint]:
    # executable JS only: supplied external scripts + inline non-JSON <script> bodies. Deliberately
    # excludes the JSON hydration blob so per-event detail URLs don't flood the endpoint leads.
    js = "\n".join(scripts or []) + "\n" + "\n".join(_EXEC_SCRIPT.findall(html))
    html_no_json = _JSON_SCRIPT.sub(" ", html)  # D2 finders scan HTML minus the hydration blobs
    found: dict[str, DiscoveredEndpoint] = {}

    def add(raw: str, source: str) -> None:
        url = _resolve(raw, base)
        if not url:
            return
        kind = classify_endpoint(url)
        event_relevant = bool(_EVENTISH.search(url))
        if kind is EndpointKind.UNKNOWN and "/api/" not in url.lower() and not event_relevant:
            return  # keep the noise down — only classified, /api, or event-relevant endpoints
        found.setdefault(url, DiscoveredEndpoint(url, kind, source, event_relevant))

    # D2 finders over the HTML (minus JSON hydration blobs)
    for u in find_api_endpoints(html_no_json, base):
        add(u, "html")
    for u in find_graphql_endpoints(html_no_json, base):
        add(u, "html")
    # JS call sites (executable JS only)
    for raw in _FETCH.findall(js):
        add(raw, "fetch")
    for raw in _AXIOS.findall(js):
        add(raw, "axios")
    for raw in _XHR.findall(js):
        add(raw, "xhr")
    for raw in _CONFIG.findall(js):
        add(raw, "config")
    for raw in _GQL_REF.findall(js):
        add(raw, "graphql")
    for raw in _PATH_LIT.findall(js):
        add(raw, "js-path")
    for raw in _URL_LIT.findall(js):
        add(raw, "js-url")

    # event-relevant endpoints first, then the rest — bounded
    ranked = sorted(found.values(), key=lambda e: (0 if e.event_relevant else 1, e.url))
    return ranked[:25]
