"""Hydration extraction (Phase 8E) — reuse D2's extractors, go deeper.

Reuses D2's `extract_next_data` / `extract_window_state` / `extract_embedded_json` /
`extract_flight_strings` / `find_event_objects` and adds Apollo/GraphQL cache, `__INITIAL_STATE__` /
`__NUXT__` / `__PRELOADED_STATE__`, webpack chunk + Vite manifest detection, and a scan of *all*
`window.__X__` globals — over the served HTML plus any supplied external JS. No JS execution.
"""

from __future__ import annotations

import re

from app.discovery.hydration import (
    count_event_signatures,
    extract_embedded_json,
    extract_flight_strings,
    extract_next_data,
    extract_window_state,
    find_event_objects,
)
from app.discovery.rendered.models import HydrationPayload, HydrationSource

_STATE_VARS = ("__INITIAL_STATE__", "__NUXT__", "__APOLLO_STATE__", "__PRELOADED_STATE__")
_GLOBAL = re.compile(r"window\.(__[A-Za-z0-9_]+__)\s*=")
_WEBPACK = re.compile(r"webpackChunk|__webpack_require__|/_next/static/chunks/", re.IGNORECASE)
_VITE = re.compile(r"/@vite/client|/assets/index-[\w-]+\.js|import\.meta\.env", re.IGNORECASE)
_GRAPHQL_CACHE = re.compile(r'"ROOT_QUERY"|__APOLLO_STATE__|"__typename"')


def _top_keys(obj) -> list[str]:
    if isinstance(obj, dict):
        return [str(k) for k in list(obj.keys())[:10]]
    if isinstance(obj, list):
        return [f"<array[{len(obj)}]>"]
    return []


def window_globals(text: str) -> list[str]:
    """All `window.__X__ =` global names present (evidence of hydration state)."""
    seen: list[str] = []
    for name in _GLOBAL.findall(text):
        if name not in seen:
            seen.append(name)
    return seen


def collect_hydration(html: str, scripts: list[str] | None = None) -> list[HydrationPayload]:
    """Every hydration/state blob in the served bytes (+ external JS), with event counts."""
    combined = html + "\n" + "\n".join(scripts or [])
    payloads: list[HydrationPayload] = []

    parsed = extract_next_data(html)
    if parsed is not None:
        count, title = find_event_objects(parsed)
        payloads.append(
            HydrationPayload(HydrationSource.NEXT_DATA.value, count, title, _top_keys(parsed))
        )

    for var in _STATE_VARS:
        state = extract_window_state(combined, var)
        if state is not None:
            count, title = find_event_objects(state)
            payloads.append(HydrationPayload(var, count, title, _top_keys(state)))

    for blob in extract_embedded_json(html):
        if parsed is not None and blob == parsed:
            continue  # __NEXT_DATA__ is also application/json — don't count it twice
        count, title = find_event_objects(blob)
        payloads.append(
            HydrationPayload(HydrationSource.EMBEDDED_JSON.value, count, title, _top_keys(blob))
        )

    flight = extract_flight_strings(html)
    if flight:
        count = count_event_signatures("\n".join(flight))
        payloads.append(HydrationPayload(HydrationSource.NEXT_FLIGHT.value, count, None, []))

    if _WEBPACK.search(combined):
        payloads.append(HydrationPayload(HydrationSource.WEBPACK.value, 0, None, []))
    if _VITE.search(combined):
        payloads.append(HydrationPayload(HydrationSource.VITE.value, 0, None, []))

    return payloads


def has_graphql_cache(html: str, scripts: list[str] | None = None) -> bool:
    return bool(_GRAPHQL_CACHE.search(html + "\n".join(scripts or [])))
