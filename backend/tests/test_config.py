"""Regression tests for Settings parsing.

Guards the bug where a comma-separated CORS_ORIGINS env value crashed settings
construction because pydantic-settings tried to JSON-decode the list field.
"""

from __future__ import annotations

from app.config import Settings


def test_cors_origins_parsed_from_comma_string(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com,http://b.com , http://c.com")
    # Construct directly (not the cached get_settings) and ignore any real .env.
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://a.com", "http://b.com", "http://c.com"]


def test_cors_origins_defaults_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings(_env_file=None)
    assert settings.cors_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
