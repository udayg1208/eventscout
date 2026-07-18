"""robots.txt fetching + parsing. The crawler MUST honor this (legality by construction).

A pragmatic subset of the Robots Exclusion Protocol: per-user-agent groups, Allow/Disallow
(longest-match, Allow wins ties), Crawl-delay, and global Sitemap directives. Deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.discovery.fetch import Fetcher

_UA_TOKEN = "eventscoutdiscoverybot"


@dataclass
class RobotsPolicy:
    allow_all: bool = True
    disallows: list[str] = field(default_factory=list)
    allows: list[str] = field(default_factory=list)
    crawl_delay: float | None = None
    sitemaps: list[str] = field(default_factory=list)

    def allowed(self, path: str) -> bool:
        if self.allow_all and not self.disallows:
            return True
        # Longest matching rule wins; on equal length an Allow beats a Disallow.
        best_len = -1
        decision = True
        for rule, allow in [(d, False) for d in self.disallows] + [(a, True) for a in self.allows]:
            if (
                rule
                and path.startswith(rule)
                and (len(rule) > best_len or (len(rule) == best_len and allow))
            ):
                best_len = len(rule)
                decision = allow
        return decision


def parse_robots(text: str, ua_token: str = _UA_TOKEN) -> RobotsPolicy:
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    agents: list[str] = []
    directives: list[tuple[str, str]] = []
    sitemaps: list[str] = []
    last_was_agent = False

    def flush() -> None:
        nonlocal agents, directives
        if agents:
            groups.append((agents, directives))
        agents, directives = [], []

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field_, _, value = line.partition(":")
        field_, value = field_.strip().lower(), value.strip()
        if field_ == "user-agent":
            if not last_was_agent and directives:
                flush()
            agents.append(value.lower())
            last_was_agent = True
        elif field_ in ("disallow", "allow", "crawl-delay"):
            directives.append((field_, value))
            last_was_agent = False
        elif field_ == "sitemap":
            sitemaps.append(value)
    flush()

    chosen: list[tuple[str, str]] | None = None
    for group_agents, group_dirs in groups:
        if ua_token in group_agents:
            chosen = group_dirs
            break
    if chosen is None:
        for group_agents, group_dirs in groups:
            if "*" in group_agents:
                chosen = group_dirs
                break

    policy = RobotsPolicy(sitemaps=sitemaps)
    if chosen is None:
        return policy
    for field_, value in chosen:
        if field_ == "disallow" and value:
            policy.disallows.append(value)
        elif field_ == "allow" and value:
            policy.allows.append(value)
        elif field_ == "crawl-delay":
            try:
                policy.crawl_delay = float(value)
            except ValueError:
                pass
    policy.allow_all = len(policy.disallows) == 0
    return policy


class RobotsCache:
    """Fetches + caches one policy per origin."""

    def __init__(self, fetcher: Fetcher, ua_token: str = _UA_TOKEN) -> None:
        self._fetcher = fetcher
        self._ua = ua_token
        self._cache: dict[str, RobotsPolicy] = {}

    async def policy(self, url: str) -> RobotsPolicy:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._cache:
            result = await self._fetcher.get(f"{origin}/robots.txt")
            self._cache[origin] = (
                parse_robots(result.text, self._ua)
                if result and result.status == 200 and result.text
                else RobotsPolicy()
            )
        return self._cache[origin]

    async def allowed(self, url: str) -> bool:
        policy = await self.policy(url)
        return policy.allowed(urlsplit(url).path or "/")
