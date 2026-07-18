"""Deterministic extraction of raw entity names from an event.

The frozen Event model has no organizer/speaker/community fields, so entities are *derived*
from `provider` + `title` + `description` + `city` + `location`. Every rule here is
deterministic (no LLM) and deliberately conservative — it prefers to miss an entity rather
than invent a wrong one. Speaker extraction is intentionally absent: the data does not exist
in the current model (Phase 5).
"""

from __future__ import annotations

import re

from app.models.event import Event

# Community-platform providers act as the host community; aggregators (luma/confstech/
# devfolio) list events they don't host, so they are not communities.
_PROVIDER_COMMUNITY = {
    "gdg": "Google Developer Groups",
    "cncf": "CNCF",
    "fossunited": "FOSS United",
    "hasgeek": "Hasgeek",
}

_COMMUNITY_TITLE_PATTERNS = [
    (re.compile(r"\bgdg\b|google developer group", re.I), "Google Developer Groups"),
    (re.compile(r"\bcncf\b|cloud native", re.I), "CNCF"),
    (re.compile(r"foss ?united", re.I), "FOSS United"),
    (re.compile(r"\bpydata\b", re.I), "PyData"),
    (re.compile(r"devops ?days", re.I), "DevOps Days"),
    (re.compile(r"women who code", re.I), "Women Who Code"),
]

# Known organizations/companies detected as whole-word keywords in the title/description.
_KNOWN_ORGS = {
    "google": "Google",
    "microsoft": "Microsoft",
    "amazon": "Amazon",
    "aws": "Amazon",
    "meta": "Meta",
    "nvidia": "NVIDIA",
    "ibm": "IBM",
    "oracle": "Oracle",
    "adobe": "Adobe",
    "github": "GitHub",
    "gitlab": "GitLab",
    "red hat": "Red Hat",
    "vmware": "VMware",
    "intel": "Intel",
    "atlassian": "Atlassian",
    "postman": "Postman",
    "mongodb": "MongoDB",
    "hugging face": "Hugging Face",
    "razorpay": "Razorpay",
    "flipkart": "Flipkart",
    "swiggy": "Swiggy",
    "zoho": "Zoho",
    "freshworks": "Freshworks",
}

_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_ORDINAL = re.compile(r"\b\d{1,2}(st|nd|rd|th)\b", re.I)
_EDITION = re.compile(r"\b(annual|edition|season|vol|volume)\b", re.I)
_STRIP_EDGES = " -–—:|,"


def extract_city(event: Event) -> str | None:
    return event.city


def extract_communities(event: Event) -> list[str]:
    found: list[str] = []
    provider_community = _PROVIDER_COMMUNITY.get(event.provider)
    if provider_community:
        found.append(provider_community)
    text = f"{event.title} {event.description or ''}"
    for pattern, name in _COMMUNITY_TITLE_PATTERNS:
        if pattern.search(text) and name not in found:
            found.append(name)
    return found


def extract_organizations(event: Event) -> list[str]:
    text = f"{event.title} {event.description or ''}".casefold()
    found: list[str] = []
    for keyword, name in _KNOWN_ORGS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", text) and name not in found:
            found.append(name)
    return found


def series_name(event: Event) -> str | None:
    """A series display name: the title with year, ordinal, edition words, and the event's
    own city removed. Conservative — only these tokens are stripped, so distinct series stay
    distinct. Returns None if nothing meaningful remains."""
    text = _YEAR.sub("", event.title)
    text = _ORDINAL.sub("", text)
    text = _EDITION.sub("", text)
    if event.city:
        text = re.sub(rf"\b{re.escape(event.city)}\b", "", text, flags=re.I)
    text = " ".join(text.split()).strip(_STRIP_EDGES)
    return text if len(text) >= 3 else None


def extract_venue(event: Event) -> str | None:
    """A venue name from `location`, when it is more specific than the bare city."""
    location = event.location
    if not location:
        return None
    venue = location.split(",")[0].strip()
    if len(venue) < 3 or venue.casefold() in {"online", "virtual"}:
        return None
    if event.city and venue.casefold() == event.city.casefold():
        return None
    return venue
