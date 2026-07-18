"""Application configuration.

All settings are read from environment variables (or a local `.env` file) via
pydantic-settings. Nothing is hardcoded and no secret ever lives in source.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "Event Discovery Agent"
    environment: str = "development"
    log_level: str = "INFO"

    # Origins allowed to call this API (the frontend). Accepts a comma-separated
    # string in the env var. NoDecode stops pydantic-settings from JSON-decoding
    # the raw value so our validator below can split it itself.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # --- Gemini (query understanding) ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-lite"

    # --- Cache ---
    cache_ttl_seconds: int = 300

    # --- Catalog (Phase 3E: search reads from the Repository, not live providers) ---
    catalog_db_path: str = "catalog.db"  # SQLite file for the event catalog (Postgres later)
    provider_state_db_path: str = "provider_state.db"  # SQLite file for provider state
    search_candidate_limit: int = 500  # bounded candidate window ranked per search
    search_cache_ttl_seconds: int = 60  # read-path search cache TTL

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Allow CORS_ORIGINS to be provided as "a,b,c" in the environment."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read the environment only once)."""
    return Settings()
