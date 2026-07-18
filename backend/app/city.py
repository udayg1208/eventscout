"""Canonical Indian city-name normalization.

Applied at the provider boundary so events from different sources (which use
"Bengaluru" vs "Bangalore", "Bombay" vs "Mumbai", ...) all carry the same city,
and so a query city matches regardless of spelling.
"""

from __future__ import annotations

import re

# alias (casefolded) -> canonical display name
_CANONICAL: dict[str, str] = {
    "bengaluru": "Bangalore",
    "bangalore": "Bangalore",
    "bombay": "Mumbai",
    "mumbai": "Mumbai",
    "gurugram": "Gurgaon",
    "gurgaon": "Gurgaon",
    "new delhi": "Delhi",
    "delhi": "Delhi",
    "madras": "Chennai",
    "chennai": "Chennai",
    "calcutta": "Kolkata",
    "kolkata": "Kolkata",
    "cochin": "Kochi",
    "kochi": "Kochi",
    "trivandrum": "Thiruvananthapuram",
    "thiruvananthapuram": "Thiruvananthapuram",
    "pune": "Pune",
    "hyderabad": "Hyderabad",
    "noida": "Noida",
    "ahmedabad": "Ahmedabad",
    "jaipur": "Jaipur",
    "chandigarh": "Chandigarh",
    "goa": "Goa",
}


def normalize_city(name: str | None) -> str | None:
    """Return the canonical city name, or the trimmed input if unknown/None."""
    if name is None:
        return None
    trimmed = name.strip()
    if not trimmed:
        return trimmed
    return _CANONICAL.get(trimmed.casefold(), trimmed)


def detect_city(*texts: str | None) -> str | None:
    """Return the first canonical city whose name appears as a whole word in any
    of the given texts (e.g. a venue or chapter string), else None.

    Used by text-oriented providers to recover a city from free-text fields.
    Longest aliases are tried first so "New Delhi" wins over "Delhi".
    """
    for text in texts:
        if not text:
            continue
        low = text.casefold()
        for alias in sorted(_CANONICAL, key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", low):
                return _CANONICAL[alias]
    return None
