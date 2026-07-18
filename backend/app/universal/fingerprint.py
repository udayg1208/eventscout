"""Incremental extraction (Phase 10B) — fingerprint a page, skip it if unchanged.

A content fingerprint (sha1 over whitespace-normalized bytes) lets the engine skip re-extracting a
page that hasn't changed since last time — the cheap path for continuous/scheduled re-runs.
In-memory here; a durable store is a trivial swap. Deterministic.
"""

from __future__ import annotations

import hashlib
import re

_WS = re.compile(r"\s+")


def fingerprint(html: str) -> str:
    normalized = _WS.sub(" ", html).strip()
    return hashlib.sha1(normalized.encode("utf-8", "ignore")).hexdigest()


class FingerprintStore:
    def __init__(self) -> None:
        self._seen: dict[str, str] = {}

    def unchanged(self, url: str, fp: str) -> bool:
        return self._seen.get(url) == fp

    def remember(self, url: str, fp: str) -> None:
        self._seen[url] = fp

    def size(self) -> int:
        return len(self._seen)
