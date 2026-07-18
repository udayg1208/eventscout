"""Ingestion layer — the production path from a provider into the catalog.

    ProviderPlugin -> Capability Registry -> Sandbox validation -> Normalize ->
    Classify -> Entity Resolution -> Bulk Upsert -> Provider State -> Analytics

Wraps the existing providers as plugins (their fetch logic is untouched) and drives one
complete ingestion via the Runner. No scheduler or workers live here.
"""

from app.ingestion.plugin import ProviderCapabilities, ProviderPlugin
from app.ingestion.registry import ProviderRegistry, build_registry
from app.ingestion.runner import IngestionReport, render_report, run_ingestion
from app.ingestion.sandbox import SandboxReport, render_sandbox_report, run_sandbox

__all__ = [
    "ProviderPlugin",
    "ProviderCapabilities",
    "ProviderRegistry",
    "build_registry",
    "run_ingestion",
    "IngestionReport",
    "render_report",
    "run_sandbox",
    "SandboxReport",
    "render_sandbox_report",
]
