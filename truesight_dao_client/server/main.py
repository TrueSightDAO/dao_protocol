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

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .. import __version__
from .config import Settings, get_settings
from .routes import dao, design, events_catalog, health, proxy, qr_code_check, query, shipping, stripe_order_sync, stripe_subscription, subscription_obligation, tracking


def _configure_bugsnag(settings: Settings) -> bool:
    """Configure Bugsnag if an API key is set. Empty key → no-op (SDK not even imported)."""
    if not settings.bugsnag_api_key:
        return False
    import bugsnag  # imported lazily so the package is only required when a key is set

    bugsnag.configure(
        api_key=settings.bugsnag_api_key,
        release_stage=settings.environment,
        app_version=__version__,
        project_root="/home/ubuntu/dao_protocol",
    )
    return True


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
    if _configure_bugsnag(settings):
        from bugsnag.asgi import BugsnagMiddleware

        app.add_middleware(BugsnagMiddleware)

    # Mirror Edgar's global rack-cors (config/initializers/cors.rb): any origin, all methods,
    # no credentials, 2h preflight cache. Required for the agroverse.shop browser `fetch` to
    # /agroverse_shop/shipping_rates (PR4); harmless for the server-to-server routes.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
        max_age=7200,
    )

    # Serve the static landing page at / (exact root only — API routes take precedence).
    static_dir = Path(__file__).resolve().parent / "static"
    index_html = static_dir / "index.html"

    @app.get("/", include_in_schema=False)
    async def root():
        return FileResponse(str(index_html))

    app.include_router(events_catalog.router, tags=["events_catalog"])
    app.include_router(health.router, tags=["health"])
    app.include_router(proxy.router, tags=["proxy"])
    app.include_router(tracking.router, tags=["tracking"])
    app.include_router(shipping.router, tags=["shipping"])
    app.include_router(dao.router, tags=["dao"])
    app.include_router(qr_code_check.router, tags=["qr_code_check"])
    app.include_router(qr_code_check.router, prefix="/agroverse", tags=["qr_code_check"])
    app.include_router(stripe_order_sync.router, tags=["stripe_order_sync"])
    app.include_router(stripe_subscription.router, tags=["stripe_subscription"])
    app.include_router(subscription_obligation.router, tags=["subscription_obligation"])
    app.include_router(query.router, tags=["dao_query"])
    app.include_router(design.router, tags=["design"])
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
