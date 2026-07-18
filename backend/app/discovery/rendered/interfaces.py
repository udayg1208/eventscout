"""Future rendered-discovery seams (Phase 8E) — INTERFACES ONLY, no implementations.

8E reasons deterministically over the served bytes with no browser and no network. These mark where
later phases plug in: a real LLM reasoner, a browser renderer (execute JS to obtain the hydrated
DOM), and an API prober (call a discovered endpoint to confirm event count). Each raises
`NotImplementedError`. None of these run in 8E — no JS execution, no network, no auth.
"""

from __future__ import annotations

from abc import abstractmethod

from app.discovery.rendered.models import DiscoveredEndpoint, ProviderCandidate
from app.discovery.rendered.reasoning import AIReasoner


class GeminiReasoner(AIReasoner):
    """FUTURE: a real LLM reasoner (Gemini/OpenAI) using prompts.py + a strict JSON schema.

    Reasons over the same extracted signals the mock does, but with genuine understanding of
    arbitrary hydration shapes — under the same never-fabricate / cite-evidence / UNKNOWN contract.
    """

    name = "gemini"

    def reason(
        self, url, *, framework, hydration, endpoints, html
    ) -> ProviderCandidate:  # pragma: no cover
        raise NotImplementedError("real LLM reasoning is deferred — 8E uses MockAIReasoner")


class BrowserRenderer:
    """FUTURE (Phase 8E+): execute a page's JS to obtain the hydrated DOM (SPAs that expose nothing
    in the served bytes). Out of 8E's no-browser scope; documented as the next capability."""

    @abstractmethod
    async def render(self, url: str, html: str) -> str:  # pragma: no cover
        raise NotImplementedError("browser rendering is deferred — no browser automation in 8E")


class ApiProber:
    """FUTURE: call a discovered endpoint (public, GET, rate-limited) to confirm its event count.

    8E only *records* endpoints as leads; probing needs network and is deliberately deferred."""

    @abstractmethod
    async def probe(self, endpoint: DiscoveredEndpoint) -> int:  # pragma: no cover
        raise NotImplementedError("endpoint probing is deferred — 8E never calls an endpoint")
