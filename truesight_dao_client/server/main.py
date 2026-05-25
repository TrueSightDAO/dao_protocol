"""FastAPI application factory + uvicorn entrypoint for the dao_protocol server.

Run locally::

    pip install -e .[server]
    truesight-dao-protocol-server                 # uses DAO_PROTOCOL_* env / .env
    # or:
    uvicorn truesight_dao_client.server.main:app --port 8010

PR1 mounts only the health router. Later slices register the dao / shipping /
meta_checkout / newsletter / email_agent / proxy / qr_code routers here.
"""

from __future__ import annotations

from fastapi import FastAPI

from .. import __version__
from .config import get_settings
from .routes import health


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TrueSight DAO protocol service",
        version=__version__,
        description=(
            "DAO/Agroverse integration surface extracted from the Rails Edgar "
            "app. See agentic_ai_context/EDGAR_DAO_EXTRACTION_PLAN.md."
        ),
    )
    app.include_router(health.router, tags=["health"])
    return app


# Module-level app for `uvicorn truesight_dao_client.server.main:app`.
app = create_app()


def main() -> None:
    """Console-script entrypoint (`truesight-dao-protocol-server`)."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "truesight_dao_client.server.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
