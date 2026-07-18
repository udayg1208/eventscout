"""Graph deduplication (Phase 8C) — one node per real thing.

Canonicalizes URLs (reusing D1's `normalize_url` + tracking-param stripping, honoring a page's
`<link rel=canonical>` and redirect target) so that the same URL, its canonical, its redirects, and
its tracking-decorated variants all collapse to a single node key. Feeds/calendars key by their own
canonical URL; pages/sources key by `type#canonical-url`.
"""

from __future__ import annotations

import re

from app.discovery.expansion.models import NodeType
from app.discovery.urls import normalize_url, registrable_domain

_TRACKING = re.compile(r"(?i)(^utm_|^gclid$|^fbclid$|^ref$|^ref_src$|^mc_cid$|^mc_eid$|^igshid$)")


def _strip_tracking(url: str) -> str:
    if "?" not in url:
        return url
    base, query = url.split("?", 1)
    kept = [p for p in query.split("&") if p and not _TRACKING.match(p.split("=", 1)[0])]
    return f"{base}?{'&'.join(kept)}" if kept else base


def canonicalize(
    url: str, *, canonical: str | None = None, redirect_target: str | None = None
) -> str | None:
    """Best canonical form: prefer explicit canonical/redirect, then normalize + strip tracking."""
    chosen = redirect_target or canonical or url
    normalized = normalize_url(_strip_tracking(chosen))
    return normalized


def node_key(node_type: NodeType, canonical_url: str) -> str:
    """Dedup identity for a node. Feeds/calendars are per-URL; a domain node keys by its domain."""
    if node_type is NodeType.DOMAIN:
        return f"domain#{registrable_domain(canonical_url)}"
    return f"{node_type.value}#{canonical_url}"
