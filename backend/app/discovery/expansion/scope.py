"""Scope Engine (Phase 8C) — never crawl forever.

Decides, for each candidate URL, whether the crawler may follow it: same-domain and same-registrable
-domain are always in scope; a curated set of trusted external platforms may be crossed once;
blocklisted domains are refused; anything past the depth limit or otherwise unknown is out of scope
(it may still be *recorded* as a reference node, just not crawled).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.discovery.urls import registrable_domain

# Platforms we allow the crawler to cross into (one hop) because they host events/communities.
DEFAULT_TRUSTED_EXTERNAL = frozenset(
    {
        "meetup.com",
        "community.dev",
        "gdg.community.dev",
        "fossunited.org",
        "hasgeek.com",
        "lu.ma",
        "commudle.com",
        "eventbrite.com",
        "devfolio.co",
        "townscript.com",
    }
)
# Never crawl these — social/aggregator/commerce hosts that would explode the frontier.
DEFAULT_BLOCKED = frozenset(
    {
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "youtube.com",
        "amazon.in",
        "flipkart.com",
        "bookmyshow.com",
    }
)


class ScopeDecision(StrEnum):
    ALLOW = "allow"  # same domain
    CROSS_TRUSTED = "cross_trusted"  # trusted external platform (one hop)
    BLOCK = "block"  # blocklisted host
    DEPTH_EXCEEDED = "depth_exceeded"
    OUT_OF_SCOPE = "out_of_scope"  # record as reference, don't crawl


@dataclass
class ScopeConfig:
    seed_domains: set[str] = field(default_factory=set)
    trusted_external: frozenset[str] = DEFAULT_TRUSTED_EXTERNAL
    blocked: frozenset[str] = DEFAULT_BLOCKED
    max_depth: int = 2


def evaluate_scope(url: str, *, depth: int, config: ScopeConfig) -> tuple[ScopeDecision, str]:
    domain = registrable_domain(url)
    if domain in config.blocked:
        return ScopeDecision.BLOCK, f"blocked host {domain}"
    if depth > config.max_depth:
        return ScopeDecision.DEPTH_EXCEEDED, f"depth {depth} > {config.max_depth}"
    if domain in config.seed_domains:
        return ScopeDecision.ALLOW, f"in-scope domain {domain}"
    if domain in config.trusted_external:
        return ScopeDecision.CROSS_TRUSTED, f"trusted external {domain}"
    return ScopeDecision.OUT_OF_SCOPE, f"out-of-scope host {domain}"


def is_crawlable(decision: ScopeDecision) -> bool:
    return decision in (ScopeDecision.ALLOW, ScopeDecision.CROSS_TRUSTED)
