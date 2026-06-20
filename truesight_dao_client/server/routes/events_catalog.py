"""Canonical DAO events catalog — single source of truth served as JSON.

GET /events-catalog  → serve the canonical events catalog
GET /events-catalog/healthz → health check (catalog loadable)

Used by Sophia autopilot and other clients that need live event definitions.
Served at edgar.truesight.me/events-catalog
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

router = APIRouter()
logger = logging.getLogger("dao_protocol.events_catalog")

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "events_catalog.json"

_cached_catalog: bytes | None = None
_cached_catalog_mtime: float | None = None


def _load_catalog() -> bytes:
    global _cached_catalog, _cached_catalog_mtime
    try:
        mtime = _CATALOG_PATH.stat().st_mtime
        if _cached_catalog is not None and _cached_catalog_mtime == mtime:
            return _cached_catalog
        raw = _CATALOG_PATH.read_bytes()
        # Validate it's parseable JSON
        json.loads(raw)
        _cached_catalog = raw
        _cached_catalog_mtime = mtime
        return raw
    except Exception as exc:
        logger.error("Failed to load events catalog: %s", exc)
        if _cached_catalog is not None:
            return _cached_catalog
        return json.dumps({"error": "Events catalog unavailable"}).encode()


@router.get("/events-catalog", include_in_schema=True)
async def events_catalog() -> Response:
    return Response(content=_load_catalog(), media_type="application/json")


@router.get("/events-catalog/healthz", include_in_schema=False)
async def catalog_healthz() -> JSONResponse:
    try:
        data = json.loads(_load_catalog())
        event_count = len(data.get("events", {}))
        return JSONResponse({"status": "ok", "event_count": event_count, "version": data.get("version")})
    except Exception as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=500)
