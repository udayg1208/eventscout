"""Capability Registry — the one authoritative list of providers + declared capabilities.

This is the *only* place provider-specific knowledge lives, and it lives as **data**:
each entry pairs an unmodified provider with its capabilities and operational config.
The rest of the pipeline reads these declarations — never the provider's identity — so
there is no `if provider == ...` anywhere downstream.

Capabilities are declared *honestly*: today's providers yield only what the current
Event model can carry, so speaker/organizer/schedule/delta flags are False across the
board and flip on individually as providers gain those features (Phase 5+).
"""

from __future__ import annotations

from app.ingestion.plugin import ProviderCapabilities, ProviderPlugin
from app.providers.atlassian import AtlassianProvider
from app.providers.base import EventProvider
from app.providers.cncf import CNCFProvider
from app.providers.confstech import ConfsTechProvider
from app.providers.devfolio import DevfolioProvider
from app.providers.devpost import DevpostProvider
from app.providers.eventbrite import EventbriteProvider
from app.providers.fossunited import FOSSUnitedProvider
from app.providers.gdg import GDGProvider
from app.providers.hasgeek import HasgeekProvider
from app.providers.ics import ICSProvider
from app.providers.ics_sources import ICS_SOURCES, IcsSource
from app.providers.luma import LumaProvider
from app.providers.meetup import MeetupProvider
from app.providers.salesforce import SalesforceProvider
from app.providers.snowflake import SnowflakeProvider
from app.providers.unstop import UnstopProvider
from app.rendering import BrowserRenderedProvider


class ProviderRegistry:
    """Holds the installed plugins; the pipeline's single source of provider truth."""

    def __init__(self, plugins: list[ProviderPlugin]) -> None:
        self._plugins = {plugin.id: plugin for plugin in plugins}

    def all(self) -> list[ProviderPlugin]:
        return list(self._plugins.values())

    def ids(self) -> list[str]:
        return list(self._plugins)

    def get(self, provider_id: str) -> ProviderPlugin | None:
        return self._plugins.get(provider_id)

    def with_capability(self, name: str) -> list[ProviderPlugin]:
        """Every plugin that declares capability `name` — capability-driven selection,
        the intended alternative to per-provider conditionals."""
        return [p for p in self._plugins.values() if getattr(p.capabilities, name, False)]


def _plugin(
    provider: EventProvider,
    *,
    id: str,
    name: str,
    capabilities: ProviderCapabilities,
    refresh_interval_seconds: float,
    expected_volume: int,
    timeout_seconds: float = 30.0,
) -> ProviderPlugin:
    return ProviderPlugin(
        id=id,
        name=name,
        version=1,
        provider=provider,
        capabilities=capabilities,
        refresh_interval_seconds=refresh_interval_seconds,
        timeout_seconds=timeout_seconds,
        expected_volume=expected_volume,
    )


def _ics_plugin(source: IcsSource) -> ProviderPlugin:
    """Turn one curated ICS feed into a plugin — the config-driven, hierarchical path.
    Every source in `ICS_SOURCES` becomes its own provider with its own id/health/refresh,
    generated from data (no per-source code)."""
    return _plugin(
        ICSProvider(
            name=source.id,
            ics_url=source.ics_url,
            city=source.city,
            category=source.category,
        ),
        id=source.id,
        name=source.name,
        capabilities=ProviderCapabilities(),  # ICS: dates + location only
        refresh_interval_seconds=21_600,  # 6h — community feeds move slowly
        expected_volume=source.expected_volume,
        timeout_seconds=20.0,
    )


def build_registry() -> ProviderRegistry:
    """Construct the production registry: hand-listed API providers + the config-driven
    ICS family (one plugin per curated feed).

    Refresh cadence is tiered by source velocity; capabilities reflect what each source
    actually supplies today."""
    plugins = [
        _plugin(
            ConfsTechProvider(),
            id="confstech",
            name="Confs.tech",
            capabilities=ProviderCapabilities(),  # static dataset: dates + city only
            refresh_interval_seconds=86_400,  # daily — a curated static list
            expected_volume=15,
        ),
        _plugin(
            DevfolioProvider(),
            id="devfolio",
            name="Devfolio",
            capabilities=ProviderCapabilities(supports_online_events=True, supports_pricing=True),
            refresh_interval_seconds=3_600,
            expected_volume=16,
        ),
        _plugin(
            GDGProvider(),
            id="gdg",
            name="Google Developer Groups",
            capabilities=ProviderCapabilities(supports_pagination=True),  # Bevy pages
            refresh_interval_seconds=3_600,
            expected_volume=14,
        ),
        _plugin(
            CNCFProvider(),
            id="cncf",
            name="CNCF Community",
            capabilities=ProviderCapabilities(supports_pagination=True),
            refresh_interval_seconds=3_600,
            expected_volume=5,
        ),
        _plugin(
            FOSSUnitedProvider(),
            id="fossunited",
            name="FOSS United",
            capabilities=ProviderCapabilities(supports_pricing=True),
            refresh_interval_seconds=21_600,  # 6h
            expected_volume=14,
        ),
        _plugin(
            HasgeekProvider(),
            id="hasgeek",
            name="Hasgeek",
            capabilities=ProviderCapabilities(),
            refresh_interval_seconds=21_600,
            expected_volume=7,
            timeout_seconds=45.0,  # fans out to per-project pages
        ),
        _plugin(
            LumaProvider(),
            id="luma",
            name="Lu.ma",
            capabilities=ProviderCapabilities(supports_online_events=True),
            refresh_interval_seconds=3_600,
            expected_volume=44,
            timeout_seconds=45.0,  # fans out to per-city pages
        ),
        # --- Phase 3G expansion (Bevy community platforms + hackathons) ---
        _plugin(
            AtlassianProvider(),
            id="atlassian",
            name="Atlassian Community Events",
            capabilities=ProviderCapabilities(supports_pagination=True),  # Bevy pages
            refresh_interval_seconds=10_800,  # 3h
            expected_volume=17,
        ),
        _plugin(
            SalesforceProvider(),
            id="salesforce",
            name="Salesforce Trailblazer Community",
            capabilities=ProviderCapabilities(supports_pagination=True),
            refresh_interval_seconds=10_800,
            expected_volume=29,
        ),
        _plugin(
            SnowflakeProvider(),
            id="snowflake",
            name="Snowflake User Groups",
            capabilities=ProviderCapabilities(supports_pagination=True),
            refresh_interval_seconds=21_600,  # 6h
            expected_volume=6,
        ),
        _plugin(
            DevpostProvider(),
            id="devpost",
            name="Devpost",
            capabilities=ProviderCapabilities(supports_online_events=True),
            refresh_interval_seconds=21_600,
            expected_volume=9,
        ),
        # --- Phase 11A catalog-expansion: India's largest student/tech opportunity platform ---
        _plugin(
            UnstopProvider(),
            id="unstop",
            name="Unstop",
            capabilities=ProviderCapabilities(
                supports_online_events=True, supports_pagination=True
            ),
            refresh_interval_seconds=10_800,  # 3h
            expected_volume=200,
            timeout_seconds=60.0,  # fans out across opportunity types + pages
        ),
        # --- Phase 11B coverage-expansion: Meetup find-page (thousands of India tech groups) ---
        _plugin(
            MeetupProvider(),
            id="meetup",
            name="Meetup",
            capabilities=ProviderCapabilities(
                supports_online_events=True, supports_pagination=True
            ),
            refresh_interval_seconds=86_400,  # daily — a wide keyword×city sweep, kept polite
            expected_volume=700,
            timeout_seconds=240.0,  # fans out across a large keyword × city matrix
        ),
        # --- Phase 11B coverage-expansion: Eventbrite public discovery (primary organizers) ---
        _plugin(
            EventbriteProvider(),
            id="eventbrite",
            name="Eventbrite",
            capabilities=ProviderCapabilities(
                supports_online_events=True, supports_pagination=True
            ),
            refresh_interval_seconds=21_600,  # 6h
            expected_volume=600,
            timeout_seconds=180.0,  # keyword × location sweep
        ),
        # --- Phase 11D Browser Rendering: events that only exist after JavaScript executes ---
        _plugin(
            BrowserRenderedProvider(),
            id="rendered",
            name="Browser Rendered (JS)",
            capabilities=ProviderCapabilities(supports_online_events=True),
            refresh_interval_seconds=86_400,  # daily — a headless-browser sweep is expensive
            expected_volume=60,
            timeout_seconds=600.0,  # renders ~a dozen JS-heavy pages in a real browser
        ),
    ]
    # Config-driven ICS family: one provider per curated feed (grows via ics_sources.py).
    plugins += [_ics_plugin(source) for source in ICS_SOURCES]
    return ProviderRegistry(plugins)
