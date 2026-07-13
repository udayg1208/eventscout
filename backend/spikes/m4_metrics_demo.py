"""Demo: GET /debug/metrics after some pipeline activity (not a test)."""

from __future__ import annotations

import json
import logging

logging.disable(logging.CRITICAL)  # keep output clean

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

client.post("/search", json={"query": "free AI webinars in Bangalore"})   # Gemini + provider
client.post("/search", json={"query": "free AI webinars in Bangalore"})   # fully cached
client.post("/events/search", json={"city": "Pune"})                      # structured (no Gemini)

print(json.dumps(client.get("/debug/metrics").json(), indent=2))
