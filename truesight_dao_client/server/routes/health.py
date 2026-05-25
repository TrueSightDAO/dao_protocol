"""Health / liveness endpoints — the PR1 plumbing-proof slice.

These prove the full path works end to end: client → krake_ng nginx →
seni_ror_new:8010 → this service. They intentionally touch nothing external
(no Sheets, no Stripe), so a green response means routing + deploy are sound.

Note: ``/ping`` mirrors Edgar's existing health route name so it can serve as
the first nginx flip, but the deploy step should route a *dedicated* path
(e.g. ``/dao-protocol/ping``) rather than hijacking Edgar's ``/ping`` until
we're confident — see EDGAR_DAO_EXTRACTION_PLAN.md.
"""

from __future__ import annotations

from fastapi import APIRouter

from ... import __version__
from ..config import get_settings

router = APIRouter()


def _payload() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": __version__,
        "environment": settings.environment,
    }


@router.get("/ping")
def ping() -> dict:
    return _payload()


@router.get("/healthz")
def healthz() -> dict:
    return _payload()
