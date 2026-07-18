"""Phase 3B: storage repository v2.

Exercises the scale-ready surface through the SQLite implementation: set-based bulk
upsert (insert / touch-unchanged / rewrite-with-version-bump / in-batch key collapse),
keyset pagination + streaming iteration, the status lifecycle (expire → archive), bulk
status changes, candidate lookup, full-field round-trip, and on-disk persistence across a
reopen. No network; in-memory except the durability test.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from app.models.event import Event, EventCategory
from app.storage.models import (
    EventStatus,
    SearchCriteria,
    StoredEvent,
    content_hash,
    event_key,
)
from app.storage.sqlite_repository import SQLiteEventRepository


def run(coro):
    return asyncio.run(coro)


async def _drain(aiter):
    return [item async for item in aiter]


T0 = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)
TODAY = date(2026, 7, 15)


def _event(
    title="Sample Event",
    *,
    start=date(2026, 9, 1),
    end=None,
    city="Bangalore",
    category=EventCategory.MEETUP,
    provider="a",
    url=None,
    description=None,
    is_free=None,
    price=None,
    location=None,
    is_online=False,
) -> Event:
    return Event(
        title=title,
        url=url or f"https://{provider}.example.com/{title.replace(' ', '-').lower()}",
        description=description,
        city=city,
        location=location,
        is_online=is_online,
        start_date=start,
        end_date=end,
        category=category,
        is_free=is_free,
        price=price,
        provider=provider,
    )


def _stored(event: Event, *, seen_at: datetime = T0) -> StoredEvent:
    return StoredEvent.from_event(event, seen_at=seen_at)


def _repo() -> SQLiteEventRepository:
    return SQLiteEventRepository()


# --------------------------- key / hash ---------------------------


def test_event_key_canonicalizes_url():
    assert event_key(_event(url="https://www.Foo.com/AB/?utm=x#frag")) == "foo.com/ab"


def test_event_key_stable_across_url_variants():
    a = event_key(_event(url="https://foo.com/ab"))
    b = event_key(_event(url="https://www.foo.com/ab/?x=1#y"))
    assert a == b


def test_event_key_disambiguates_host_only_urls():
    # Two distinct events sharing one host-only landing page must NOT collide.
    a = _event("AI Summit", url="https://hub.example.com", provider="p")
    b = _event("Cloud Day", url="https://hub.example.com", provider="p")
    assert event_key(a) != event_key(b)
    assert event_key(a).startswith("hub.example.com#")


def test_content_hash_changes_with_content():
    base = _event("A", description="x")
    assert content_hash(base) == content_hash(_event("A", description="x"))
    assert content_hash(base) != content_hash(_event("A", description="y"))


def test_from_event_defaults_active_version_one():
    record = StoredEvent.from_event(_event("A"), seen_at=T0)
    assert record.status is EventStatus.ACTIVE
    assert record.version == 1
    assert record.first_seen_at == T0 and record.last_seen_at == T0


# --------------------------- bulk upsert ---------------------------


def test_bulk_upsert_inserts_new():
    repo = _repo()
    result = run(repo.bulk_upsert([_stored(_event("A")), _stored(_event("B"))]))
    assert (result.inserted, result.updated, result.unchanged) == (2, 0, 0)
    assert run(repo.count(SearchCriteria())) == 2


def test_bulk_upsert_unchanged_touches_last_seen_keeps_first_seen_and_version():
    repo = _repo()
    event = _event("A")
    run(repo.bulk_upsert([_stored(event, seen_at=T0)]))
    result = run(repo.bulk_upsert([_stored(event, seen_at=T1)]))

    assert (result.inserted, result.updated, result.unchanged) == (0, 0, 1)
    stored = run(repo.get(event_key(event)))
    assert stored.first_seen_at == T0 and stored.last_seen_at == T1
    assert stored.version == 1  # unchanged content ⇒ no version bump


def test_bulk_upsert_rewrites_and_bumps_version_preserving_first_seen():
    repo = _repo()
    run(repo.bulk_upsert([_stored(_event("A", description="v1"), seen_at=T0)]))
    run(repo.bulk_upsert([_stored(_event("A", description="v2"), seen_at=T1)]))
    result = run(repo.bulk_upsert([_stored(_event("A", description="v3"), seen_at=T1)]))

    assert result.updated == 1
    stored = run(repo.get(event_key(_event("A"))))
    assert stored.event.description == "v3"
    assert stored.version == 3  # bumped twice
    assert stored.first_seen_at == T0  # preserved across rewrites


def test_bulk_upsert_collapses_duplicate_keys_in_one_batch():
    repo = _repo()
    # Same key twice in a single batch → one row (last wins).
    result = run(
        repo.bulk_upsert(
            [_stored(_event("A", description="first")), _stored(_event("A", description="second"))]
        )
    )
    assert result.inserted == 1
    assert run(repo.count(SearchCriteria())) == 1
    assert run(repo.get(event_key(_event("A")))).event.description == "second"


# --------------------------- read filters ---------------------------


def _titles(page):
    return [r.event.title for r in page.items]


def test_search_filters_by_city():
    repo = _repo()
    run(
        repo.bulk_upsert(
            [_stored(_event("A", city="Bangalore")), _stored(_event("B", city="Delhi"))]
        )
    )
    assert _titles(run(repo.search(SearchCriteria(city="Bangalore")))) == ["A"]


def test_search_filters_by_category():
    repo = _repo()
    run(
        repo.bulk_upsert(
            [
                _stored(_event("A", category=EventCategory.MEETUP)),
                _stored(_event("B", category=EventCategory.WORKSHOP)),
            ]
        )
    )
    assert _titles(run(repo.search(SearchCriteria(categories=[EventCategory.WORKSHOP])))) == ["B"]


def test_search_filters_by_date_range():
    repo = _repo()
    run(
        repo.bulk_upsert(
            [
                _stored(_event("early", start=date(2026, 9, 1))),
                _stored(_event("mid", start=date(2026, 9, 10))),
                _stored(_event("late", start=date(2026, 9, 20))),
            ]
        )
    )
    page = run(repo.search(SearchCriteria(date_from=date(2026, 9, 5), date_to=date(2026, 9, 15))))
    assert _titles(page) == ["mid"]


def test_search_free_only():
    repo = _repo()
    run(
        repo.bulk_upsert(
            [
                _stored(_event("free", is_free=True)),
                _stored(_event("paid", is_free=False)),
                _stored(_event("unknown", is_free=None)),
            ]
        )
    )
    assert _titles(run(repo.search(SearchCriteria(free_only=True)))) == ["free"]


def test_search_keywords_match_title_or_description():
    repo = _repo()
    run(
        repo.bulk_upsert(
            [
                _stored(_event("AI Summit")),
                _stored(_event("Cloud Workshop", description="hands-on kubernetes")),
            ]
        )
    )
    assert _titles(run(repo.search(SearchCriteria(keywords=["ai"])))) == ["AI Summit"]
    assert _titles(run(repo.search(SearchCriteria(keywords=["kubernetes"])))) == ["Cloud Workshop"]


def test_search_active_only_excludes_non_active():
    repo = _repo()
    run(
        repo.bulk_upsert([_stored(_event("past", start=date(2020, 1, 1))), _stored(_event("live"))])
    )
    run(repo.expire_ended(today=TODAY))
    assert _titles(run(repo.search(SearchCriteria(active_only=True)))) == ["live"]
    both = _titles(run(repo.search(SearchCriteria(active_only=False))))
    assert set(both) == {"past", "live"}


def test_search_upcoming_excludes_ended():
    repo = _repo()
    run(
        repo.bulk_upsert(
            [
                _stored(_event("past", start=date(2026, 1, 1), end=date(2026, 1, 2))),
                _stored(_event("future", start=date(2026, 9, 1))),
            ]
        )
    )
    assert _titles(run(repo.search(SearchCriteria(upcoming_on_or_after=TODAY)))) == ["future"]


# --------------------------- keyset pagination + iteration ---------------------------


def test_keyset_pagination_walks_all_rows_once_in_order():
    repo = _repo()
    days = [date(2026, 9, d) for d in (1, 5, 9, 13, 17)]
    run(repo.bulk_upsert([_stored(_event(f"E{i}", start=d)) for i, d in enumerate(days)]))

    seen, cursor, pages = [], None, 0
    while True:
        page = run(repo.search(SearchCriteria(limit=2, cursor=cursor)))
        seen.extend(r.event.start_date for r in page.items)
        pages += 1
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert seen == days  # every row once, in (start_date, key) order
    assert pages == 3  # 2 + 2 + 1


def test_iterate_streams_everything():
    repo = _repo()
    run(repo.bulk_upsert([_stored(_event(f"E{i}", start=date(2026, 9, 1 + i))) for i in range(5)]))
    streamed = run(_drain(repo.iterate(SearchCriteria(), batch_size=2)))
    assert len(streamed) == 5
    assert [s.event.start_date for s in streamed] == [date(2026, 9, 1 + i) for i in range(5)]


# --------------------------- lifecycle: expire / archive / status ---------------------------


def test_expire_ended_marks_only_past_and_is_idempotent():
    repo = _repo()
    past = _event("past", start=date(2026, 1, 1))
    run(repo.bulk_upsert([_stored(past), _stored(_event("future"))]))

    assert run(repo.expire_ended(today=TODAY)) == 1
    stored = run(repo.get(event_key(past)))
    assert stored is not None and stored.status is EventStatus.EXPIRED  # retained, not deleted
    assert run(repo.expire_ended(today=TODAY)) == 0  # idempotent


def test_archive_before_moves_expired_to_cold():
    repo = _repo()
    run(repo.bulk_upsert([_stored(_event("old", start=date(2026, 1, 1)))]))
    run(repo.expire_ended(today=TODAY))  # → expired
    moved = run(repo.archive_before(cutoff=date(2026, 6, 1)))
    assert moved == 1
    stored = run(repo.get(event_key(_event("old", start=date(2026, 1, 1)))))
    assert stored.status is EventStatus.ARCHIVED


def test_bulk_set_status():
    repo = _repo()
    run(repo.bulk_upsert([_stored(_event("A")), _stored(_event("B"))]))
    affected = run(
        repo.bulk_set_status(
            [event_key(_event("A"))], EventStatus.WITHDRAWN, reason="source removed"
        )
    )
    assert affected == 1
    a = run(repo.get(event_key(_event("A"))))
    assert a.status is EventStatus.WITHDRAWN and a.status_reason == "source removed"


# --------------------------- get_many / candidates ---------------------------


def test_get_many():
    repo = _repo()
    run(repo.bulk_upsert([_stored(_event("A")), _stored(_event("B")), _stored(_event("C"))]))
    got = run(repo.get_many([event_key(_event("A")), event_key(_event("C")), "missing"]))
    assert set(got) == {event_key(_event("A")), event_key(_event("C"))}


def test_find_candidates_returns_same_date_active_only():
    repo = _repo()
    day = date(2026, 9, 1)
    run(
        repo.bulk_upsert(
            [
                _stored(_event("same1", start=day)),
                _stored(_event("same2", start=day)),
                _stored(_event("other", start=date(2026, 9, 2))),
                _stored(_event("ended", start=date(2026, 1, 1))),
            ]
        )
    )
    run(repo.expire_ended(today=TODAY))  # "ended" becomes non-active
    candidates = run(repo.find_candidates(on_date=day))
    assert {c.event.title for c in candidates} == {"same1", "same2"}


# --------------------------- fidelity / durability ---------------------------


def test_roundtrip_preserves_all_fields():
    repo = _repo()
    original = Event(
        title="Full Event",
        description="Everything populated",
        url="https://a.example.com/full",
        city="Bangalore",
        location="Whitefield, Bangalore",
        is_online=True,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 3),
        category=EventCategory.CONFERENCE,
        is_free=False,
        price="₹1,999",
        provider="hasgeek",
    )
    run(repo.bulk_upsert([_stored(original)]))
    stored = run(repo.get(event_key(original)))
    assert stored.event == original


def test_get_missing_returns_none():
    assert run(_repo().get("does-not-exist")) is None


def test_file_db_persists_across_reopen(tmp_path):
    path = str(tmp_path / "events.db")
    repo = SQLiteEventRepository(path)
    run(repo.bulk_upsert([_stored(_event("A")), _stored(_event("B"))]))
    run(repo.close())

    reopened = SQLiteEventRepository(path)
    try:
        assert run(reopened.count(SearchCriteria())) == 2
        assert run(reopened.get(event_key(_event("A")))) is not None
    finally:
        run(reopened.close())
