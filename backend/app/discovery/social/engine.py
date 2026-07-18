"""Social Discovery Engine (Phase 8D) — public pages → Discovery Inbox.

Routes each (url, html) page to the matching public-platform extractor (LinkedIn / GitHub / Discord
/ Telegram / Notion / blog / forum), applies the safety gate (reject login walls, paywalls,
off-topic — never bypass auth), scores it, and upserts a Discovery Inbox candidate (discovered_by=
`status=NEW`). Fixture-driven: it consumes HTML that a future 8B/8C fetch (or a test) supplies — it
does not fetch, log in, or run a browser. Output stops at the Discovery Inbox.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.discovery.social import blog, discord, forum, github, linkedin, notion, telegram
from app.discovery.social.extractor import safety_check
from app.discovery.social.normalizer import to_candidate
from app.discovery.social.priority import score
from app.discovery.social.store import SocialRecord, SocialStore
from app.discovery.store import DiscoveryInbox

# Order matters: specific hosts first, generator-based forum last.
_PLATFORMS = [linkedin, github, discord, telegram, notion, blog, forum]


@dataclass
class SocialDiscoveryReport:
    processed: int = 0
    matched: int = 0
    unmatched: int = 0
    rejected: int = 0
    inserted: int = 0
    updated: int = 0
    extracted_events: int = 0
    by_platform: dict = field(default_factory=dict)
    rejections: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class SocialDiscoveryEngine:
    def __init__(
        self,
        inbox: DiscoveryInbox,
        *,
        store: SocialStore | None = None,
        historical_yield: dict[str, float] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inbox = inbox
        self._store = store
        self._historical = historical_yield or {}
        self._clock = clock

    async def discover(self, pages: list[tuple[str, str]]) -> SocialDiscoveryReport:
        report = SocialDiscoveryReport()
        for url, html in pages:
            report.processed += 1
            mod = next((m for m in _PLATFORMS if m.matches(url, html)), None)
            if mod is None:
                report.unmatched += 1
                continue
            report.matched += 1
            platform = mod.PLATFORM.value
            report.by_platform[platform] = report.by_platform.get(platform, 0) + 1

            now = self._clock()
            ex = mod.extract(url, html, now=now)
            passed, reasons = safety_check(url, html, ex)
            if not passed:
                report.rejected += 1
                report.rejections.append({"url": url, "platform": platform, "reasons": reasons})
                await self._save(ex, platform, {}, {"passed": False, "reasons": reasons})
                continue

            priority = score(ex, historical_yield=self._historical.get(platform, 0.0))
            outcome = await self._inbox.upsert(to_candidate(ex, priority, now=now))
            report.inserted += outcome == "inserted"
            report.updated += outcome == "updated"
            if ex.title.is_known or ex.date.is_known:
                report.extracted_events += 1
            await self._save(ex, platform, priority.as_dict(), {"passed": True})
        return report

    async def _save(self, ex, platform, priority_dict, safety) -> None:
        if self._store is not None:
            await self._store.save(
                SocialRecord(ex.url, platform, ex.as_dict(), priority_dict, safety)
            )
