"""APIEndpointDetector + GraphQLDetector — client API/GraphQL endpoints referenced in the HTML.

A SPA that hides its events behind a client-side API still *names* that API in its bundle/markup
(fetch paths, config). Discovering the endpoint gives a candidate source to probe in a later
phase. Deterministic regex over the raw HTML; never called.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.discovery.urls import normalize_url

_API_PATH = re.compile(r'["\'`](/api/[A-Za-z0-9_\-/.]{2,80})["\'`]')
_API_ABS = re.compile(
    r'["\'`](https?://[A-Za-z0-9.\-]*api[A-Za-z0-9.\-]*/[A-Za-z0-9_\-/.]{0,80})["\'`]'
)
_GQL = re.compile(
    r'["\'`]((?:https?://[A-Za-z0-9.\-]+)?/(?:graphql|gql)[A-Za-z0-9_\-/]*)["\'`]', re.IGNORECASE
)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def find_api_endpoints(html: str, base: str) -> list[str]:
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(base))
    found: list[str] = []
    for path in _API_PATH.findall(html):
        norm = normalize_url(origin + path)
        if norm:
            found.append(norm)
    for absolute in _API_ABS.findall(html):
        norm = normalize_url(absolute)
        if norm:
            found.append(norm)
    # event endpoints first (more relevant), then the rest — bounded
    ranked = sorted(_dedupe(found), key=lambda u: 0 if re.search(r"event", u, re.IGNORECASE) else 1)
    return ranked[:20]


def find_graphql_endpoints(html: str, base: str) -> list[str]:
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(base))
    found: list[str] = []
    for ref in _GQL.findall(html):
        target = ref if ref.startswith("http") else origin + ref
        norm = normalize_url(target)
        if norm:
            found.append(norm)
    return _dedupe(found)[:5]
