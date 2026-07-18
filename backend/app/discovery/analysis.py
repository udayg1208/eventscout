"""D2 framework analysis — the orchestrator that turns raw HTML into framework-based detections.

Runs FrameworkDetector + hydration/state/embedded-JSON extractors + endpoint detectors, finds
embedded event objects, and emits FeedDetections (NEXT_DATA / NEXT_FLIGHT / HYDRATION_STATE /
EMBEDDED_JSON for embedded events; JSON_API / GRAPHQL for discovered endpoints) plus the D2
signal patch and the candidate framework fields. Deterministic; no JS execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.discovery.endpoints import find_api_endpoints, find_graphql_endpoints
from app.discovery.feeds import FeedDetection
from app.discovery.fetch import FetchResult
from app.discovery.frameworks import detect_framework
from app.discovery.hydration import (
    count_event_signatures,
    extract_embedded_json,
    extract_flight_strings,
    extract_next_data,
    extract_window_state,
    find_event_objects,
)
from app.discovery.models import FeedType

_STATE_VARS = ("__NUXT__", "__APOLLO_STATE__", "__INITIAL_STATE__", "__PRELOADED_STATE__")
_HYDRATION_MARKERS = ("__NEXT_DATA__", "__next_f", *_STATE_VARS)
_CALENDAR_SCHEMA = re.compile(r'"events?"\s*:\s*\[', re.IGNORECASE)


@dataclass
class FrameworkAnalysis:
    framework: str | None = None
    framework_version: str | None = None
    hydration_source: str | None = None
    embedded_event_count: int = 0
    api_endpoints: list[str] = field(default_factory=list)
    graphql_endpoints: list[str] = field(default_factory=list)
    detections: list[FeedDetection] = field(default_factory=list)
    signals: dict[str, bool] = field(default_factory=dict)


def _best_events(html: str) -> tuple[int, str | None, str | None, bool]:
    """Best embedded-event extraction across payloads → (count, source_label, title, json_array)."""
    count, source, title, json_array = 0, None, None, False

    parsed = extract_next_data(html)
    if parsed is not None:
        json_array = True
        c, t = find_event_objects(parsed)
        if c > count:
            count, source, title = c, "__NEXT_DATA__", t

    for var in _STATE_VARS:
        state = extract_window_state(html, var)
        if state is not None:
            json_array = True
            c, t = find_event_objects(state)
            if c > count:
                count, source, title = c, var, t

    for blob in extract_embedded_json(html):
        json_array = True
        c, t = find_event_objects(blob)
        if c > count:
            count, source, title = c, "embedded_json", t

    # RSC Flight (App Router): decode the pushed strings so escaped JSON (\"startDate\":…) becomes
    # scannable, then count event signatures in the decoded text. Full Flight parsing is deferred
    # (D3) — this deterministic proxy is enough to flag the page as event-bearing.
    flight = extract_flight_strings(html)
    if flight:
        json_array = True
        fc = count_event_signatures("\n".join(flight))
        if fc > count:
            count, source = fc, "__next_f"

    # fallback: still-unparseable payloads (Nuxt2 function body) → text signature proxy on raw HTML
    if count == 0:
        text_count = count_event_signatures(html)
        if text_count > 0:
            count = text_count
            source = (
                "__next_f"
                if "__next_f" in html
                else ("__NEXT_DATA__" if parsed is not None else "embedded")
            )

    return count, source, title, json_array


_SOURCE_TO_FEED = {
    "__NEXT_DATA__": FeedType.NEXT_DATA,
    "__next_f": FeedType.NEXT_FLIGHT,
    "embedded_json": FeedType.EMBEDDED_JSON,
    "embedded": FeedType.EMBEDDED_JSON,
}


def analyze_frameworks(result: FetchResult) -> FrameworkAnalysis:
    html = result.text
    fw = detect_framework(html)
    count, source, title, json_array = _best_events(html)
    api = find_api_endpoints(html, result.url)
    gql = find_graphql_endpoints(html, result.url)

    detections: list[FeedDetection] = []
    if count > 0 and source:
        feed_type = _SOURCE_TO_FEED.get(source, FeedType.HYDRATION_STATE)
        detections.append(FeedDetection(feed_type, result.url, count, title))
    for endpoint in api:
        if re.search(r"event", endpoint, re.IGNORECASE):
            detections.append(FeedDetection(FeedType.JSON_API, endpoint, 0, None))
    for endpoint in gql[:1]:
        detections.append(FeedDetection(FeedType.GRAPHQL, endpoint, 0, None))

    has_hydration = bool(source) or any(m in html for m in _HYDRATION_MARKERS)
    signals = {
        "has_framework": fw.name is not None,
        "has_nextjs": fw.name == "Next.js" or "__NEXT_DATA__" in html or "__next_f" in html,
        "has_hydration": has_hydration,
        "has_embedded_events": count > 0,
        "has_json_array": json_array or "[{" in html,
        "has_calendar_schema": bool(_CALENDAR_SCHEMA.search(html)),
        "has_api_endpoint": len(api) > 0,
        "has_graphql_endpoint": len(gql) > 0,
    }
    return FrameworkAnalysis(
        framework=fw.name,
        framework_version=fw.version,
        hydration_source=source,
        embedded_event_count=count,
        api_endpoints=api,
        graphql_endpoints=gql,
        detections=detections,
        signals=signals,
    )
