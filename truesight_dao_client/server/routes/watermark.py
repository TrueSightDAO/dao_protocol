"""POST /dao/read_watermark_gps — read the burned-in Timemark watermark GPS off a photo.

A1.1 of ``plans/TREE_PLANTING_PHOTO_GPS_CAPTURE_PLAN.md`` (agentic_ai_context).

The CFR (``cfr_main.html``) and SunMint (``report_tree_planting.html``) DApps call this
*after* EXIF and ``navigator.geolocation`` both come up empty and *before* they sign the
``[TREE PLANTING EVENT]`` text. The coordinates must be inside the signed ``requestText``:
the RSA signature is computed client-side over the exact text, so a server-side append
would break verification.

Boundaries (the plan's A1 acceptance criteria):
  * READ-ONLY / SIDE-EFFECT-FREE — crops + OCRs a temp copy of the upload, deletes it,
    writes nothing (no Sheets, no ledger, no persistence).
  * BOUNDED — the whole read runs under a wall-clock cap (``read_watermark_timeout_s``).
    A slow/failed call MUST be treated by the caller as "no coords" and the submission
    proceeds as it does today: losing GPS on an occasional call is recoverable (hand
    backfill), losing the farmer's whole submission is not.
  * HONEST SOURCE — a success returns ``source="watermark"`` so the DApp can stamp
    ``- GPS Source: watermark`` and a vision-read value stays auditable vs a device-typed
    one (mirrors the 17 coords backfilled by hand).
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..vision import timemark_watermark as tw

router = APIRouter()
logger = logging.getLogger("dao_protocol.watermark")

# Accepted multipart field names for the photo (``attachment`` matches the DApp's
# existing ``/dao/submit_contribution`` upload field).
_FILE_FIELDS = ("attachment", "file")

# Suffix fallback so the reader's Pillow open gets a hint when the upload has no name.
_DEFAULT_SUFFIX = ".jpg"


def _to_decimal(value: object, ref: object, refs: str) -> float | None:
    """Signed decimal degrees from the reader's (value, hemisphere) pair.

    ``refs`` is the two accepted hemisphere letters (``"NS"`` / ``"EW"``). Returns
    ``None`` — never a guess — when the value is missing/unnumeric or the hemisphere
    letter is absent, so a garbled read can never masquerade as a real coordinate.
    """
    if value is None or value == "":
        return None
    try:
        num = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    letter = str(ref or "").strip().upper()[:1]
    # NB: compare against a tuple, not the string -- ``"" in "NS"`` is True in Python,
    # which would let a blank hemisphere masquerade as a valid value.
    if letter not in tuple(refs):
        return None
    return -num if letter in ("S", "W") else num


def _shape(result: dict) -> dict:
    """Normalize the reader's dict into the endpoint's stable JSON contract."""
    result = result or {}
    lat = _to_decimal(result.get("lat"), result.get("lat_ref"), "NS")
    lon = _to_decimal(result.get("lon"), result.get("lon_ref"), "EW")
    if lat is None or lon is None:
        return {
            "lat": None,
            "lon": None,
            "source": None,
            "method": result.get("method"),
            "code": result.get("code"),
            "status": "no_watermark",
        }
    return {
        "lat": lat,
        "lon": lon,
        "source": "watermark",
        "method": result.get("method"),
        "code": result.get("code"),
        "status": "ok",
    }


def _run_reader(path: str, allow_vision: bool) -> dict:
    """Run the tested reader; OCR-only unless ``allow_vision`` (keeps the hot path fast)."""
    if allow_vision:
        return tw.read_timemark_watermark(path)
    # Explicit no-op vision fn: run the local OCR pass only. A caller that wants the
    # (slower) Gemini fallback opts in, so the pre-signing path is never blocked on it.
    return tw.read_timemark_watermark(path, vision_fn=lambda _regions: "")


def _null(status: str) -> dict:
    return {
        "lat": None,
        "lon": None,
        "source": None,
        "method": None,
        "code": None,
        "status": status,
    }


@router.post("/dao/read_watermark_gps")
async def read_watermark_gps(request: Request) -> JSONResponse:
    settings = get_settings()
    form = await request.form()

    upload = None
    for field in _FILE_FIELDS:
        candidate = form.get(field)
        if candidate is not None and hasattr(candidate, "read"):
            upload = candidate
            break
    if upload is None:
        return JSONResponse(
            {
                "error": "missing_attachment",
                "status": "error",
                "message": f"Attach the field photo as a multipart '{_FILE_FIELDS[0]}' field.",
            },
            status_code=400,
        )

    data = await upload.read()
    if not data:
        return JSONResponse(
            {**_null("error"), "error": "empty_attachment"}, status_code=400
        )
    if len(data) > settings.read_watermark_max_bytes:
        return JSONResponse(
            {**_null("error"), "error": "payload_too_large"},
            status_code=413,
        )

    suffix = (
        os.path.splitext(getattr(upload, "filename", "") or "")[1] or _DEFAULT_SUFFIX
    )
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        os.write(fd, data)
        os.close(fd)
        allow_vision = str(form.get("allow_vision") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        result = await asyncio.wait_for(
            run_in_threadpool(_run_reader, path, allow_vision),
            timeout=settings.read_watermark_timeout_s,
        )
    except asyncio.TimeoutError:
        # Slow read → the caller proceeds without coords (never a hard failure).
        logger.warning(
            "read_watermark_gps timed out after %ss", settings.read_watermark_timeout_s
        )
        return JSONResponse(_null("timeout"))
    except Exception as exc:  # noqa: BLE001 - never make the DApp's submit fail on us
        logger.warning("read_watermark_gps failed: %s", exc)
        return JSONResponse(_null("error"))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    return JSONResponse(_shape(result))
