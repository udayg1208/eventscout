"""Browser Rendered provider — events that exist ONLY after JavaScript executes.

The browser (`BrowserRenderer`) replaces the fetch step; extraction is the **existing Universal
Event Engine** (Phase 10B) — unchanged. For each JS-heavy target we render the page, feed the final
DOM *plus* the captured runtime JSON/GraphQL payloads (injected as embedded `<script>` JSON so the
engine's existing embedded-JSON extractor reads them) into `UniversalEventEngine.extract`, then map
the extracted `UniversalEvent`s onto the catalogue `Event` model. Everything downstream — the
ingestion validator, cross-provider dedup, the catalog — is reused as-is. The engine's extraction is
wrapped defensively so a single malformed page can never abort a whole ingestion cycle.

These sources (Commudle/Angular, 10times, Townscript, Konfhub, …) returned **zero** events to the
raw-HTML providers; every event here is discoverable *only because browser rendering exists*.
"""

from __future__ import annotations

import logging
from datetime import date
from urllib.parse import urljoin

from app.cache import TTLCache
from app.city import normalize_city
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.categorize import category_from_title
from app.providers.filtering import matches
from app.rendering.browser import BrowserRenderer, RenderedPage
from app.universal import UniversalEventEngine

logger = logging.getLogger(__name__)

PROVIDER_NAME = "rendered"
_CACHE_KEY = "rendered:all"
_DATA_TTL_SECONDS = 3600

# JS-rendered target listings — each returned 0 events to raw-HTML fetching (proven in Phase 11A–C).
DEFAULT_TARGETS: tuple[str, ...] = (
    "https://www.commudle.com/events",
    "https://www.commudle.com/hackathons",
    "https://10times.com/bengaluru-in/technology",
    "https://10times.com/newdelhi-in/technology",
    "https://10times.com/mumbai-in/technology",
    "https://10times.com/pune-in/technology",
    "https://10times.com/hyderabad-in/technology",
    "https://10times.com/chennai-in/technology",
    "https://10times.com/bengaluru-in/it-technology",
    "https://10times.com/india/technology",
    "https://www.townscript.com/india",
    "https://www.townscript.com/discover/all/technology",
)

# event-type hint (from the Universal Engine) -> catalogue category
_CATEGORY: dict[str, EventCategory] = {
    "hackathon": EventCategory.HACKATHON,
    "conference": EventCategory.CONFERENCE,
    "workshop": EventCategory.WORKSHOP,
    "meetup": EventCategory.MEETUP,
    "webinar": EventCategory.WEBINAR,
    "summit": EventCategory.CONFERENCE,
    "expo": EventCategory.CONFERENCE,
    "talk": EventCategory.MEETUP,
}
# JSON payloads carrying these keys are event data worth injecting for the engine to read
_EVENT_JSON_HINTS = ('"start_date"', '"start_time"', '"starttime"', '"event_name"', '"eventname"')
_MAX_INJECT = 6
_MAX_INJECT_BYTES = 800_000

# General aggregators (10times/Townscript) list every kind of event, so a rendered event from them
# is kept only when its title/description reads as tech. Dev-only platforms (Commudle) are exempt.
_TECH_HOSTS_EXEMPT = ("commudle.com",)
_TECH = (
    "ai", "artificial intelligence", "machine learning", "deep learning", "data", "analytics",
    "code", "coding", "hack", "developer", "devops", "tech", "software", "engineer", "cloud",
    "aws", "azure", "gcp", "docker", "kubernetes", "python", "java", "javascript", "typescript",
    "react", "angular", "vue", "node", "web", "api", "cyber", "security", "infosec", "blockchain",
    "web3", "crypto", "iot", "robot", "vr", "ar/", "game", "ui/ux", "product", "startup", "founder",
    "saas", "llm", "genai", "gen ai", "agent", "mcp", "open source", "foss", "linux", "database",
    "sql", "mongodb", "postgres", "spark", "kafka", "snowflake", "gpu", "pytorch", "tensorflow",
    "langchain", "digital", "innovation", "computing", "computational", "network", "automation",
    "quantum", "embedded", "frontend", "backend", "flutter", "android", "ios", "rust", "golang",
    "nlp", "natural language", "computer vision", "programming", "hackathon", "devfest", "pydata",
    "pycon", "gdg", "technology", "electronics", "semiconductor", "fintech", "edtech", "design",
    "ieee", "acm", "ciso", "cto", "cio", "informatics", "it ", "sysadmin", "service desk",
    "intelligence", "systems",
)


def _is_tech(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in _TECH)


def _parse_date(raw) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])  # normalized ISO; date part is the first 10 chars
    except ValueError:
        return None


def _augment(page: RenderedPage) -> str:
    """Final DOM + the runtime JSON/GraphQL payloads injected as embedded JSON, so the engine's
    existing embedded-JSON extractor can read XHR-only events (no extraction code changes)."""
    blocks = []
    seen: set[str] = set()
    for _url, body in page.json_payloads:
        low = body.lower()
        if len(body) > _MAX_INJECT_BYTES or not any(h in low for h in _EVENT_JSON_HINTS):
            continue
        if body in seen:
            continue
        seen.add(body)
        blocks.append(f'<script type="application/json" data-rendered-xhr="1">{body}</script>')
        if len(blocks) >= _MAX_INJECT:
            break
    if not blocks:
        return page.dom
    return page.dom.replace("</body>", "".join(blocks) + "</body>", 1) or page.dom + "".join(blocks)


class BrowserRenderedProvider(EventProvider):
    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        renderer: BrowserRenderer | None = None,
        engine: UniversalEventEngine | None = None,
        targets: tuple[str, ...] = DEFAULT_TARGETS,
        ttl_seconds: float = _DATA_TTL_SECONDS,
        today: date | None = None,
        min_confidence: float = 0.15,
    ) -> None:
        self._renderer = renderer or BrowserRenderer()
        self._engine = engine or UniversalEventEngine()
        self._targets = targets
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)
        self._today = today
        self._min_conf = min_confidence

    async def search(self, query: SearchQuery) -> list[Event]:
        events = self._cache.get(_CACHE_KEY)
        if events is None:
            events = await self._load()
            if events:
                self._cache.set(_CACHE_KEY, events)
        return [event for event in events if matches(event, query)]

    async def _load(self) -> list[Event]:
        today = self._today or date.today()
        seen: set[str] = set()
        events: list[Event] = []
        try:
            for url in self._targets:
                page = await self._renderer.render(url)
                if not page.ok:
                    continue
                html = _augment(page)
                try:
                    report = await self._engine.extract(url, html)
                except Exception as exc:  # noqa: BLE001 — reuse the frozen engine, survive its bugs
                    logger.warning("rendered: extract failed for %s: %s", url, type(exc).__name__)
                    continue
                for ue in report.events:
                    if not ue.valid or ue.confidence < self._min_conf:
                        continue
                    event = self._to_event(ue, url)
                    if event is None:
                        continue
                    # tech-gate general aggregators (keep dev-only platforms as-is)
                    if not any(h in url for h in _TECH_HOSTS_EXEMPT) and not _is_tech(
                        f"{event.title} {event.description or ''}"
                    ):
                        continue
                    key = str(event.url) + "|" + event.title.lower()
                    if key in seen or (event.end_date or event.start_date) < today:
                        continue
                    seen.add(key)
                    events.append(event)
        finally:
            await self._renderer.close()
        logger.info(
            "rendered: %d events from %d rendered pages", len(events), self._renderer.rendered_count
        )
        return events

    def _to_event(self, ue, source_url: str) -> Event | None:
        title = ue.title
        if not title or not title.strip():
            return None
        start = _parse_date(ue.get("start_date"))
        if start is None:
            return None
        end = _parse_date(ue.get("end_date"))
        if end == start:
            end = None
        reg = ue.get("registration_url")
        url = urljoin(source_url, reg) if reg else source_url
        mode = (ue.get("mode") or "").lower()
        is_online = mode in ("online", "virtual", "remote")
        city = ue.get("city")
        etype = (ue.get("event_type") or "").lower()
        category = _CATEGORY.get(etype) or category_from_title(title, default=EventCategory.MEETUP)
        try:
            return Event(
                title=title.strip(),
                description=ue.get("description"),
                url=url,
                city=None if is_online else (normalize_city(city) if city else None),
                location="Online" if is_online else (ue.get("venue") or city),
                is_online=is_online,
                start_date=start,
                end_date=end,
                category=category,
                is_free=None,
                price=None,
                provider=PROVIDER_NAME,
            )
        except Exception:  # noqa: BLE001 — a malformed extracted field must not abort the batch
            return None
