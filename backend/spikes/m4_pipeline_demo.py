"""M4 demo (not a test): show POST /search end-to-end with pipeline logs.

Two identical requests: the second must be served from cache without calling Gemini
or the provider. Run:
    cd backend
    ./.venv/Scripts/python.exe -m spikes.m4_pipeline_demo
"""

from __future__ import annotations

import json
import logging

logging.basicConfig(level=logging.INFO, format="LOG | %(name)s | %(message)s", force=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
QUERY = "free AI webinars in Bangalore"


def show(label: str, body: dict) -> None:
    print(
        f">>> {label}: cached={body['cached']} count={body['count']} "
        f"query={json.dumps(body['query'])}"
    )


print("\n===== 1st POST /search (expect parse MISS + results MISS) =====")
show("first", client.post("/search", json={"query": QUERY}).json())

print("\n===== 2nd POST /search (expect parse HIT + results HIT, no Gemini) =====")
show("second", client.post("/search", json={"query": QUERY}).json())
