"""Future social-discovery seams (Phase 8D) — INTERFACES ONLY.

8D consumes public HTML that a caller supplies. These abstractions mark where later phases feed it:
a `SocialPageFeed` that hands over public pages fetched by 8B/8C, and a `RenderedSocialExtractor`
for SPA social pages (Phase 8E). Each raises `NotImplementedError`.

NOT a seam, ever: authenticated/private access. 8D is public-content-only by design — logging in,
joining servers, or reading private groups is permanently out of scope, not a future feature.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.discovery.social.models import SocialExtraction


class SocialPageFeed(ABC):
    """FUTURE: supply public social pages (url, html) fetched by 8B/8C for the engine to process."""

    @abstractmethod
    async def public_pages(self) -> list[tuple[str, str]]:  # pragma: no cover
        raise NotImplementedError("wiring 8B/8C-fetched public pages into 8D is a future step")


class RenderedSocialExtractor(ABC):
    """FUTURE (Phase 8E): extract from a JS-rendered social page. Still no auth — public only.

    8D is HTML-only, so a client-rendered social page (many are) yields little. A future renderer
    would supply the post-hydration public DOM here — never a logged-in session.
    """

    @abstractmethod
    async def extract_rendered(
        self, url: str, rendered_html: str
    ) -> SocialExtraction:  # pragma: no cover
        raise NotImplementedError("browser-rendered social extraction is Phase 8E (public only)")
