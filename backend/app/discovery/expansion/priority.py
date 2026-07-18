"""Priority Engine (Phase 8C) — every discovered URL gets an explainable ExpansionPriority.

Never random: a URL's crawl priority is a weighted sum of deterministic signals read from the URL +
anchor text (feed/calendar/"events"/"meetup"/"chapter"/"community"/"conference"/"hackathon"/
"workshop") plus context (a trusted domain, a known organizer, and the discovering domain's trust).
Every score carries its reasons.
"""

from __future__ import annotations

import re

from app.discovery.expansion.models import ExpansionPriority

WEIGHTS = {
    "feed": 0.20,
    "calendar": 0.18,
    "events": 0.12,
    "meetup": 0.12,
    "chapter": 0.08,
    "community": 0.08,
    "conference": 0.08,
    "hackathon": 0.06,
    "workshop": 0.04,
    "trusted_domain": 0.10,
    "known_organizer": 0.10,
    "domain_trust": 0.10,
}

_PATTERNS = {
    "feed": re.compile(r"/(feed|rss|atom)\b|\.(xml|rss)\b", re.I),
    "calendar": re.compile(r"\.ics\b|calendar|/cal\b", re.I),
    "events": re.compile(r"\bevents?\b|/e/", re.I),
    "meetup": re.compile(r"\bmeetups?\b|meetup\.com", re.I),
    "chapter": re.compile(r"\bchapter\b", re.I),
    "community": re.compile(r"\bcommunity\b|community\.dev|user ?group", re.I),
    "conference": re.compile(r"\bconf(erence)?\b|\bsummit\b|devfest", re.I),
    "hackathon": re.compile(r"\bhackathons?\b|devfolio", re.I),
    "workshop": re.compile(r"\bworkshops?\b|\bbootcamp\b", re.I),
}


def score_url(
    url: str,
    *,
    anchor_text: str = "",
    trusted_domain: bool = False,
    known_organizer: bool = False,
    domain_trust: float = 0.0,
) -> ExpansionPriority:
    text = f"{url} {anchor_text}".lower()
    signals: dict[str, float | bool] = {}
    reasons: list[str] = []
    score = 0.0

    for name, pattern in _PATTERNS.items():
        hit = bool(pattern.search(text))
        signals[name] = hit
        if hit:
            score += WEIGHTS[name]
            reasons.append(f"{name}(+{WEIGHTS[name]:.2f})")

    if trusted_domain:
        signals["trusted_domain"] = True
        score += WEIGHTS["trusted_domain"]
        reasons.append("trusted_domain")
    if known_organizer:
        signals["known_organizer"] = True
        score += WEIGHTS["known_organizer"]
        reasons.append("known_organizer")
    dt = max(0.0, min(1.0, domain_trust))
    if dt > 0:
        signals["domain_trust"] = round(dt, 3)
        score += WEIGHTS["domain_trust"] * dt
        reasons.append(f"domain_trust({dt:.2f})")

    return ExpansionPriority(score=round(min(1.0, score), 4), signals=signals, reasons=reasons)
