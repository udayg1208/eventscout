"""Phase 3C: the ingestion pipeline.

Network-free: a FakeProvider stands in for a real source (configurable to return
events, fail N times, or hang), so the whole path — plugin -> registry -> sandbox ->
normalize -> classify -> entity-resolution -> bulk upsert -> provider state -> report —
is exercised end to end without any network or production coupling.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, date, datetime

from app.ingestion import plugin as plugin_mod
from app.ingestion import runner as runner_mod
from app.ingestion import sandbox as sandbox_mod
from app.ingestion import stages as stages_mod
from app.ingestion.plugin import ProviderPlugin
from app.ingestion.registry import build_registry
from app.ingestion.runner import run_ingestion
from app.ingestion.sandbox import run_sandbox
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.storage.models import SearchCriteria
from app.storage.sqlite_provider_state import SQLiteProviderStateStore
from app.storage.sqlite_repository import SQLiteEventRepository


def run(coro):
    return asyncio.run(coro)


async def _nosleep(_seconds: float) -> None:
    return None


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
TODAY = date(2026, 7, 15)


class FakeProvider(EventProvider):
    """A stand-in source. Records the query it received; can fail or hang on demand."""

    name = "fake"

    def __init__(self, events=None, *, fail_times=0, hang_seconds=0.0, exc=None):
        self._events = events or []
        self._fail_times = fail_times
        self._hang = hang_seconds
        self._exc = exc or RuntimeError("provider down")
        self.calls = 0
        self.last_query: SearchQuery | None = None

    async def search(self, query: SearchQuery) -> list[Event]:
        self.calls += 1
        self.last_query = query
        if self._hang:
            await asyncio.sleep(self._hang)
        if self.calls <= self._fail_times:
            raise self._exc
        return list(self._events)


def _event(
    title="Sample",
    *,
    start=date(2026, 9, 1),
    category=EventCategory.MEETUP,
    provider="a",
    url=None,
    city="Bangalore",
    description=None,
):
    return Event(
        title=title,
        url=url or f"https://{provider}.example.com/{title.replace(' ', '-').lower()}",
        city=city,
        description=description,
        start_date=start,
        category=category,
        provider=provider,
    )


def _plugin(provider, *, id="fake", max_attempts=1, timeout=5.0):
    return ProviderPlugin(
        id=id,
        name=id,
        version=1,
        provider=provider,
        max_attempts=max_attempts,
        timeout_seconds=timeout,
    )


def _stores():
    return SQLiteEventRepository(), SQLiteProviderStateStore()


# --------------------------- plugin + registry ---------------------------


def test_plugin_fetch_delegates_with_empty_query():
    fake = FakeProvider([_event("A")])
    events = run(_plugin(fake).fetch())
    assert len(events) == 1
    assert fake.last_query == SearchQuery()  # empty query = "give me everything"


def test_registry_exposes_all_plugins_and_capabilities():
    from app.providers.ics_sources import ICS_SOURCES

    reg = build_registry()
    core = {
        "confstech",
        "devfolio",
        "gdg",
        "cncf",
        "fossunited",
        "hasgeek",
        "luma",
        "atlassian",
        "salesforce",
        "snowflake",
        "devpost",
        "unstop",  # Phase 11A catalog-expansion
        "meetup",  # Phase 11B coverage-expansion
        "eventbrite",  # Phase 11B coverage-expansion
        "rendered",  # Phase 11D browser rendering
    }
    ids = set(reg.ids())
    assert core <= ids
    # config-driven ICS family: one plugin per curated feed
    assert len(reg.all()) == len(core) + len(ICS_SOURCES)
    # the only non-core plugins are the ICS Meetup feeds (id "meetup-<slug>")
    assert all(pid.startswith("meetup-") for pid in ids - core)
    # capability-driven selection, not identity checks
    assert {p.id for p in reg.with_capability("supports_pagination")} == {
        "gdg",
        "cncf",
        "atlassian",
        "salesforce",
        "snowflake",
        "unstop",
        "meetup",
        "eventbrite",
    }
    assert reg.get("luma").capabilities.supports_online_events is True


def test_pipeline_has_no_provider_specific_logic():
    # The pipeline modules must never reference a provider by id — only the registry may.
    provider_ids = {
        "confstech",
        "devfolio",
        "gdg",
        "cncf",
        "fossunited",
        "hasgeek",
        "luma",
        "atlassian",
        "salesforce",
        "snowflake",
        "devpost",
    }
    for module in (runner_mod, sandbox_mod, stages_mod, plugin_mod):
        src = inspect.getsource(module)
        leaked = {pid for pid in provider_ids if pid in src}
        assert not leaked, f"{module.__name__} references providers {leaked}"


# --------------------------- runner: happy path ---------------------------


def test_runner_ingests_into_catalog_and_updates_state():
    repo, store = _stores()
    fake = FakeProvider([_event("Cloud Meetup"), _event("Data Meetup")])
    report = run(
        run_ingestion(_plugin(fake, id="p"), repo, store, now=NOW, today=TODAY, sleep=_nosleep)
    )

    assert report.ok and report.fetched == 2 and report.accepted == 2 and report.inserted == 2
    assert run(repo.count(SearchCriteria())) == 2

    state = run(store.get_provider_state("p"))
    assert state.total_runs == 1 and state.total_successes == 1
    assert state.checkpoint is not None
    assert state.capabilities  # registered with capability record on first run


def test_reingestion_is_incremental():
    repo, store = _stores()
    fake = FakeProvider([_event("A"), _event("B")])
    plugin = _plugin(fake, id="p")
    run(run_ingestion(plugin, repo, store, now=NOW, today=TODAY, sleep=_nosleep))
    report = run(run_ingestion(plugin, repo, store, now=NOW, today=TODAY, sleep=_nosleep))

    assert (report.inserted, report.updated, report.unchanged) == (0, 0, 2)
    assert run(repo.count(SearchCriteria())) == 2  # no duplicates on re-run
    assert run(store.get_provider_state("p")).total_runs == 2


def test_classification_is_preserved():
    repo, store = _stores()
    # a generic MEETUP whose text is clearly AI → classifier refines it to `ai`
    fake = FakeProvider([_event("Applied Machine Learning Meetup", category=EventCategory.MEETUP)])
    run(run_ingestion(_plugin(fake, id="p"), repo, store, now=NOW, today=TODAY, sleep=_nosleep))

    page = run(repo.search(SearchCriteria(categories=[EventCategory.AI])))
    assert [r.event.title for r in page.items] == ["Applied Machine Learning Meetup"]


def test_dedup_within_batch_is_preserved():
    repo, store = _stores()
    # same event, two sources (different URLs) in one batch → collapses to one
    batch = [
        _event("Tech Summit", provider="a", url="https://a.com/summit"),
        _event("Tech Summit", provider="b", url="https://b.com/summit"),
    ]
    report = run(
        run_ingestion(
            _plugin(FakeProvider(batch), id="p"), repo, store, now=NOW, today=TODAY, sleep=_nosleep
        )
    )
    assert report.accepted == 1 and report.duplicates == 1
    assert run(repo.count(SearchCriteria())) == 1


def test_cross_source_resolution_against_catalog():
    repo, store = _stores()
    # provider A ingests the event first
    run(
        run_ingestion(
            _plugin(
                FakeProvider([_event("Tech Summit", provider="a", url="https://a.com/s")]), id="a"
            ),
            repo,
            store,
            now=NOW,
            today=TODAY,
            sleep=_nosleep,
        )
    )
    assert run(repo.count(SearchCriteria())) == 1

    # provider B posts the same event under a different URL → resolved as a duplicate
    report = run(
        run_ingestion(
            _plugin(
                FakeProvider([_event("Tech Summit", provider="b", url="https://b.com/s")]), id="b"
            ),
            repo,
            store,
            now=NOW,
            today=TODAY,
            sleep=_nosleep,
        )
    )
    assert report.duplicates == 1 and report.accepted == 0
    assert run(repo.count(SearchCriteria())) == 1  # catalog stays canonical


# --------------------------- runner: failure handling ---------------------------


def test_fetch_failure_records_state_and_writes_nothing():
    repo, store = _stores()
    fake = FakeProvider(fail_times=99, exc=RuntimeError("host unreachable"))
    report = run(
        run_ingestion(
            _plugin(fake, id="p", max_attempts=2), repo, store, now=NOW, today=TODAY, sleep=_nosleep
        )
    )

    assert report.ok is False and report.errors
    assert run(repo.count(SearchCriteria())) == 0
    assert fake.calls == 2  # retried up to max_attempts

    state = run(store.get_provider_state("p"))
    assert state.total_failures == 1 and state.consecutive_failures == 1
    assert "host unreachable" in (state.last_error or "")


def test_retry_then_success():
    repo, store = _stores()
    fake = FakeProvider([_event("A")], fail_times=1)  # fail once, then succeed
    report = run(
        run_ingestion(
            _plugin(fake, id="p", max_attempts=3), repo, store, now=NOW, today=TODAY, sleep=_nosleep
        )
    )

    assert report.ok and report.accepted == 1
    assert fake.calls == 2
    assert run(store.get_provider_state("p")).total_successes == 1


def test_timeout_is_handled_as_failure():
    repo, store = _stores()
    fake = FakeProvider([_event("A")], hang_seconds=0.5)
    report = run(
        run_ingestion(
            _plugin(fake, id="p", max_attempts=1, timeout=0.01),
            repo,
            store,
            now=NOW,
            today=TODAY,
            sleep=_nosleep,
        )
    )

    assert report.ok is False
    assert run(store.get_provider_state("p")).total_failures == 1


# --------------------------- sandbox ---------------------------


def test_sandbox_previews_without_touching_storage():
    fake = FakeProvider(
        [
            _event("AI Summit", url="https://a.com/ai"),
            _event("AI Summit", url="https://b.com/ai"),  # duplicate of the first
            _event("Old Thing", start=date(2020, 1, 1)),  # stale → invalid
        ]
    )
    report = run(run_sandbox(_plugin(fake, id="p"), today=TODAY))

    assert report.ok and report.fetched == 3
    assert report.invalid == 1 and report.valid == 2
    assert report.duplicates == 1  # the two AI Summits collapse
    assert 0.0 <= report.quality_score <= 1.0
    assert report.normalized_sample  # a preview is produced
    assert any("ended" in err for err in report.validation_errors)


def test_sandbox_reports_fetch_failure():
    report = run(run_sandbox(_plugin(FakeProvider(fail_times=99), id="p"), today=TODAY))
    assert report.ok is False and report.fetched == 0 and report.passed is False
    assert report.error
