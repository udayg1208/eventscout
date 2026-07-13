"""M2.5 spike: validate Confs.tech as a real, zero-cost event source.

NOT production code. Not wired into get_provider(). Run manually:

    cd backend
    ./.venv/Scripts/python.exe -m spikes.confstech_spike

Goal: fetch real Indian tech-conference data from Confs.tech and prove it maps
cleanly into our existing Event model, so real events are interchangeable with
MockProvider output.

Data source: public GitHub JSON, no key, no auth.
  https://github.com/tech-conferences/conference-data
  conferences/<year>/<topic>.json
"""

from __future__ import annotations

from datetime import date

import httpx
from pydantic import ValidationError

from app.models.event import Event, EventCategory

RAW_BASE = (
    "https://raw.githubusercontent.com/tech-conferences/"
    "conference-data/main/conferences"
)

# Cast a wide net; missing topic files (404) are skipped.
TOPICS = [
    "general", "data", "python", "javascript", "devops", "security",
    "leadership", "product", "ux", "golang", "java", "rust", "php",
    "ruby", "dotnet", "android", "ios", "graphql", "agile", "scala",
]
YEARS = [2026, 2027]

PROVIDER_NAME = "confs.tech"


def fetch_raw_entries() -> list[dict]:
    """Download and merge all topic files, de-duplicated by URL."""
    seen: set[str] = set()
    merged: list[dict] = []
    with httpx.Client(timeout=15.0) as client:
        for year in YEARS:
            for topic in TOPICS:
                url = f"{RAW_BASE}/{year}/{topic}.json"
                resp = client.get(url)
                if resp.status_code != 200:
                    continue
                for entry in resp.json():
                    key = entry.get("url", "")
                    if key and key not in seen:
                        seen.add(key)
                        merged.append(entry)
    return merged


def normalize(entry: dict) -> Event | None:
    """Map one Confs.tech entry into our Event model, or None if unusable.

    Honest mapping decisions:
      * category is always CONFERENCE — Confs.tech only lists conferences; we do
        NOT invent workshop/hackathon types from the topic file name.
      * price / is_free stay None — the source carries no pricing at all.
    """
    try:
        start = date.fromisoformat(entry["startDate"])
    except (KeyError, ValueError):
        return None  # no usable date -> not a discoverable event

    end_raw = entry.get("endDate")
    end = date.fromisoformat(end_raw) if end_raw and end_raw != entry["startDate"] else None

    city = entry.get("city")
    country = entry.get("country")
    is_online = bool(entry.get("online", False))
    location = "Online" if is_online and not city else ", ".join(
        p for p in (city, country) if p
    ) or None

    try:
        return Event(
            title=entry["name"],
            description=None,               # source has no description field
            url=entry["url"],
            city=city,
            location=location,
            is_online=is_online,
            start_date=start,
            end_date=end,
            category=EventCategory.CONFERENCE,
            is_free=None,                   # unknown -> do not assume
            price=None,
            provider=PROVIDER_NAME,
        )
    except (KeyError, ValidationError):
        return None


def main() -> None:
    raw = fetch_raw_entries()
    print(f"Fetched {len(raw)} unique conference entries across topics/years.")

    india_raw = [e for e in raw if e.get("country") == "India"]
    print(f"Entries with country == 'India': {len(india_raw)}")

    normalized: list[Event] = []
    dropped = 0
    for entry in india_raw:
        event = normalize(entry)
        if event is None:
            dropped += 1
        else:
            normalized.append(event)

    print(f"Normalized into Event objects: {len(normalized)} (dropped {dropped})")

    upcoming = sorted(
        (e for e in normalized if e.start_date >= date.today()),
        key=lambda e: e.start_date,
    )
    print(f"Upcoming (start_date >= today): {len(upcoming)}\n")

    print("--- Sample normalized Indian events ---")
    for event in upcoming[:8]:
        print(
            f"[{event.start_date}] {event.title}\n"
            f"    where: {event.location} | online={event.is_online} | "
            f"cat={event.category.value} | price={event.price}\n"
            f"    url:   {event.url}"
        )

    # Proof of interchangeability with MockProvider: same type, same schema.
    if normalized:
        assert all(isinstance(e, Event) for e in normalized)
        print(
            "\nAll normalized results are app.models.Event instances "
            "-> interchangeable with MockProvider output."
        )


if __name__ == "__main__":
    main()
