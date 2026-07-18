"""Browser Rendering layer (Phase 11D).

A JavaScript-executing fetch step (headless Chrome via Playwright) that unlocks events which exist
only after client-side rendering / runtime XHR / GraphQL — sources the raw-HTML providers could not
see. The browser only replaces the fetch; extraction reuses the Universal Event Engine (10B) and
everything downstream (validation, dedup, catalog) is unchanged. Additive; no extraction rewrite.
"""

from __future__ import annotations

from app.rendering.browser import BrowserRenderer, RenderedPage
from app.rendering.provider import DEFAULT_TARGETS, BrowserRenderedProvider

__all__ = [
    "BrowserRenderer",
    "RenderedPage",
    "BrowserRenderedProvider",
    "DEFAULT_TARGETS",
]
