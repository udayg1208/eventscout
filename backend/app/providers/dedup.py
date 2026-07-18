"""Cross-provider deduplication (search intelligence).

Deterministic, explainable, fuzzy — via rapidfuzz (no embeddings, no vectors, no LLM).
The same event cross-posted to different providers (different titles/URLs/city
spellings) collapses to a single richest record. Every step is an isolated pure
function; see DEDUP_BREAKDOWN.md.

Efficiency: events are blocked by `start_date` (duplicates share a date), so only
same-day events are compared — clustering is near-linear on the real dataset.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from urllib.parse import urlsplit

from rapidfuzz import fuzz

from app.city import normalize_city
from app.models.event import Event
from app.providers.ranking import completeness, score_source

# Two events are duplicates when their similarity meets this threshold.
_SIMILARITY_THRESHOLD = 0.85
# A near-identical normalized URL alone confirms a duplicate.
_URL_CONFIRM = 0.95
_MAX_DATE_DELTA_DAYS = 1

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


# --------------------------- normalization ---------------------------


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return _NON_ALNUM.sub(" ", title.casefold()).strip()


def normalize_url(url: str) -> str:
    """Host + path only: drop scheme, `www.`, query, fragment, trailing slash."""
    parts = urlsplit(url)
    host = parts.netloc.casefold().removeprefix("www.")
    path = parts.path.rstrip("/").casefold()
    return f"{host}{path}"


# --------------------------- similarity ---------------------------


def title_similarity(a: str, b: str) -> float:
    """Fuzzy ratio in [0, 1]. `max(token_sort, ratio)`: token_sort handles word
    reordering, ratio handles spacing variants (e.g. "GenAI" vs "Gen AI"). We avoid
    WRatio because its partial-substring component over-matches short titles."""
    na, nb = normalize_title(a), normalize_title(b)
    return max(fuzz.token_sort_ratio(na, nb), fuzz.ratio(na, nb)) / 100.0


def url_similarity(a: str, b: str) -> float:
    """1.0 for equal normalized URLs, else a fuzzy ratio in [0, 1]."""
    na, nb = normalize_url(a), normalize_url(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return fuzz.ratio(na, nb) / 100.0


def event_similarity(a: Event, b: Event) -> float:
    """Combined similarity in [0, 1]. Hard gates on date and city prevent false
    positives; a matching URL confirms; otherwise title drives (nudged by URL)."""
    if abs((a.start_date - b.start_date).days) > _MAX_DATE_DELTA_DAYS:
        return 0.0  # different dates -> different events
    city_a, city_b = normalize_city(a.city), normalize_city(b.city)
    if city_a and city_b and city_a.casefold() != city_b.casefold():
        return 0.0  # different known cities -> different events
    url_sim = url_similarity(str(a.url), str(b.url))
    if url_sim >= _URL_CONFIRM:
        return 1.0
    return min(1.0, title_similarity(a.title, b.title) + 0.1 * url_sim)


# --------------------------- merge / conflict resolution ---------------------------


def _richness(event: Event) -> tuple:
    """Deterministic richness key — higher is better."""
    return (
        completeness(event),
        1 if event.description else 0,
        1 if event.is_free is not None else 0,
        1 if event.price else 0,
        1 if event.location else 0,
        score_source(event),
        len(event.description or ""),
    )


def choose_best_event(events: list[Event]) -> Event:
    """Keep the richest record (description/price/free flag/location/provider quality)."""
    return max(events, key=_richness)


# --------------------------- deduplicate ---------------------------


def _cluster(group: list[Event]) -> list[list[Event]]:
    """Single-link greedy clustering within a date block (stable input order)."""
    clusters: list[list[Event]] = []
    for event in group:
        for cluster in clusters:
            if any(event_similarity(event, member) >= _SIMILARITY_THRESHOLD for member in cluster):
                cluster.append(event)
                break
        else:
            clusters.append([event])
    return clusters


def deduplicate(events: list[Event]) -> list[Event]:
    """Collapse cross-provider duplicates, keeping the richest of each cluster."""
    blocks: dict[date, list[Event]] = defaultdict(list)
    for event in events:
        blocks[event.start_date].append(event)
    survivors: list[Event] = []
    for group in blocks.values():
        for cluster in _cluster(group):
            survivors.append(choose_best_event(cluster))
    return survivors
