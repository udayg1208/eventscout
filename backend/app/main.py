"""FastAPI application factory.

The `create_app()` factory keeps construction explicit and testable, and avoids
import-time side effects. `app` is exported for `uvicorn app.main:app`.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import debug, events, health, platform, search
from app.config import get_settings
from app.logging_config import setup_logging


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(search.router)
    app.include_router(events.router)
    app.include_router(platform.router)  # Phase 6B: public Platform surface (additive)
    if not settings.is_production:
        app.include_router(debug.router)
        logger.info("Debug endpoints enabled (non-production)")

    logger.info(
        "Application initialized (env=%s, version=%s)",
        settings.environment,
        __version__,
    )
    return app


app = create_app()


if __name__ == "__main__":
    # Foolproof production entrypoint: `python -m app.main`.
    # Binds 0.0.0.0:$PORT in code so the process is reachable by a platform's edge router.
    # (uvicorn's CLI default host is 127.0.0.1 — a localhost health probe can reach it, but
    # an external router cannot, which looks like "healthy in logs, hangs from outside".)
    import os

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
