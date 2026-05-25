"""GAS cross-border proxy — port of Rails `ProxyController#gas` (PR2).

`GET /proxy/gas/:name`  → forwards the raw query string to the allowlisted GAS `doGet`.
`POST /proxy/gas/:name` → forwards the raw body + Content-Type to the GAS `doPost`.
`OPTIONS`               → CORS preflight (browser fetch from other origins, e.g. localhost DApp).

Allowlist-only (`GAS_UPSTREAMS`); GAS scripts handle their own auth (RSA verification on the
event handlers), so this endpoint is unauthenticated — same posture as the Rails original.
Uses the package's existing `requests` dependency (sync; FastAPI runs it in a threadpool), so
no new server dep. Faithful behaviors: raw query passthrough, raw body passthrough, follow
redirects, 30s timeout, upstream status/content-type echoed, 502 on upstream failure.
"""

from __future__ import annotations

import requests
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ..gas_upstreams import GAS_UPSTREAMS

router = APIRouter()

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}
_TIMEOUT = 30


@router.api_route("/proxy/gas/{name}", methods=["GET", "POST", "OPTIONS"])
async def gas(name: str, request: Request) -> Response:
    if request.method == "OPTIONS":
        return Response(status_code=200, headers=dict(_CORS))

    upstream = GAS_UPSTREAMS.get(name)
    if not upstream:
        return JSONResponse(
            {"error": f"unknown gas endpoint: {name}"}, status_code=404, headers=dict(_CORS)
        )

    try:
        if request.method == "GET":
            # Forward the RAW query string (Apps Script uses `action=…`; do not re-key via a dict).
            qs = request.url.query
            url = f"{upstream}?{qs}" if qs else upstream
            upstream_response = requests.get(url, allow_redirects=True, timeout=_TIMEOUT)
        else:  # POST
            body = await request.body()
            content_type = request.headers.get("content-type") or "application/x-www-form-urlencoded"
            upstream_response = requests.post(
                upstream,
                data=body,
                headers={"Content-Type": content_type},
                allow_redirects=True,
                timeout=_TIMEOUT,
            )
    except requests.RequestException as exc:
        return JSONResponse(
            {"error": "upstream unavailable", "detail": str(exc)}, status_code=502, headers=dict(_CORS)
        )

    media_type = upstream_response.headers.get("content-type", "application/json")
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        media_type=media_type,
        headers=dict(_CORS),
    )
