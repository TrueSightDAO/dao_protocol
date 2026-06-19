"""Read-only DAO query endpoints — transactions, QR codes, inventory movements.

All endpoints return JSON and support case-insensitive substring matching on
name/partner fields. Live reads from Google Sheets using existing service accounts.

See DAO_QUERY_ENDPOINTS_PLAN.md in agentic_ai_context for the full plan.
"""

from __future__ import annotations

import logging

import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..config import get_settings
from ..sheets import inventory_movements, qr_codes, transactions

router = APIRouter(prefix="/dao", tags=["dao_query"])
logger = logging.getLogger("dao_protocol.query")


@router.get("/transactions")
async def get_transactions(
    partner: str | None = Query(None, description="Substring match on partner/buyer name"),
    sku: str | None = Query(None, description="Substring match on product/SKU"),
    from_date: str | None = Query(None, alias="from", description="Start date (YYYYMMDD, inclusive)"),
    to_date: str | None = Query(None, alias="to", description="End date (YYYYMMDD, inclusive)"),
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
):
    """Return historical sales records from the QR Code Sales tab.

    Filters are case-insensitive substring matches on partner name and SKU.
    Date range is inclusive on both ends.
    """
    results = transactions.query(
        partner=partner,
        sku=sku,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )
    return {"results": results, "count": len(results)}


@router.get("/qr-codes")
async def get_qr_codes(
    manager: str | None = Query(None, description="Substring match on manager name"),
    owner: str | None = Query(None, description="Substring match on owner"),
    sku: str | None = Query(None, description="Substring match on SKU/Currency"),
    status: str | None = Query(None, description="Exact match on status (MINTED, SOLD, SAMPLE, GIFT, etc.)"),
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
):
    """Return QR code records from the Agroverse QR codes tab.

    Filters: manager, owner, and sku are case-insensitive substring matches.
    Status is an exact match (case-insensitive).
    """
    results = qr_codes.query(
        manager=manager,
        owner=owner,
        sku=sku,
        status=status,
        limit=limit,
    )
    return {"results": results, "count": len(results)}


@router.get("/inventory-movements")
async def get_inventory_movements(
    person: str | None = Query(None, description="Substring match on sender or recipient name"),
    role: str | None = Query(None, description="Narrow to 'sender' or 'recipient'"),
    from_date: str | None = Query(None, alias="from", description="Start date (YYYYMMDD, inclusive)"),
    to_date: str | None = Query(None, alias="to", description="End date (YYYYMMDD, inclusive)"),
    limit: int = Query(100, ge=1, le=1000, description="Max rows to return"),
):
    """Return inventory movement records from the Inventory Movement tab.

    `person` matches against both sender and recipient (case-insensitive substring).
    Set `role=sender` or `role=recipient` to narrow to one column.
    """
    results = inventory_movements.query(
        person=person,
        role=role,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )
    return {"results": results, "count": len(results)}


# ── In-memory cache for the review-queue directory listing ──────────────
# GitHub Contents API has a rate limit (60/hr unauthenticated, 5000/hr authed).
# We cache the listing for 30 seconds so rapid pagination doesn't burn quota.

_review_queue_cache: dict = {"items": None, "fetched_at": None}


async def _fetch_review_queue_files() -> list[dict]:
    """Fetch the sorted list of JSON cache files from treasury-cache/review-queue/.

    Uses the GitHub Contents API. Returns an empty list if the directory
    doesn't exist or is empty. Results are cached for 30 seconds.
    """
    now = datetime.now(timezone.utc)
    if _review_queue_cache["items"] is not None and _review_queue_cache["fetched_at"] is not None:
        age = (now - _review_queue_cache["fetched_at"]).total_seconds()
        if age < 30:
            return _review_queue_cache["items"]

    settings = get_settings()
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_pat:
        headers["Authorization"] = f"Bearer {settings.github_pat}"

    url = f"https://api.github.com/repos/{settings.github_review_queue_repo}/contents/review-queue"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=15)

    if resp.status_code == 404:
        # Directory doesn't exist yet — empty queue
        _review_queue_cache["items"] = []
        _review_queue_cache["fetched_at"] = now
        return []

    if resp.status_code != 200:
        logger.warning("GitHub API returned %d for review-queue listing", resp.status_code)
        # Return stale cache if we have one, otherwise empty
        return _review_queue_cache["items"] or []

    files = resp.json()
    if not isinstance(files, list):
        return []

    # Filter to .json files only, sorted alphabetically (filename = hash key = chronological)
    json_files = sorted(
        [f for f in files if f.get("name", "").endswith(".json")],
        key=lambda f: f["name"],
    )

    _review_queue_cache["items"] = json_files
    _review_queue_cache["fetched_at"] = now
    return json_files


@router.get("/review_queue")
async def get_review_queue(
    limit: int = Query(10, ge=1, le=100, description="Max items to return (1-100)"),
    after_filename: str | None = Query(None, description="Cursor: return items after this filename"),
):
    """Return the review queue — pending contribution reviews from Scored Chatlogs.

    Reads JSON cache files from ``treasury-cache/review-queue/`` via the GitHub
    Contents API. Supports cursor-based pagination for infinite scroll.

    **First load (no cursor):** Returns the first ``limit`` files.
    **Scrolling (cursor provided):** Skips past ``after_filename``.
    **Cursor file deleted:** Skips to next available file (doesn't fail).
    **Empty queue:** Returns ``{ items: [], has_more: false }``.

    Each item contains the full JSON content of the cache file:
    - ``scoring_hash_key`` — unique row identifier
    - ``contributor_name`` — name of the contributor
    - ``contribution_description`` — what they did
    - ``tdgs_provisioned`` — Grok's suggested TDG amount
    - ``found_in_contributors`` — whether contributor resolved automatically
    - ``submitted_at`` — when the contribution was made
    - ``telegram_message_link`` — link to the original message
    """
    files = await _fetch_review_queue_files()

    if not files:
        return {"items": [], "has_more": False}

    # Find the starting index based on cursor
    start_idx = 0
    if after_filename:
        for i, f in enumerate(files):
            if f["name"] == after_filename:
                start_idx = i + 1
                break
        # If cursor file was deleted, start_idx stays 0 and we return from the beginning

    # Slice the requested page
    page = files[start_idx:start_idx + limit]
    has_more = len(files) > start_idx + limit
    next_filename = page[-1]["name"] if page and has_more else None

    # Fetch content for each file
    settings = get_settings()
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_pat:
        headers["Authorization"] = f"Bearer {settings.github_pat}"

    items = []
    async with httpx.AsyncClient() as client:
        for f in page:
            try:
                content_url = f["download_url"]
                resp = await client.get(content_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    data["_filename"] = f["name"]
                    items.append(data)
                else:
                    # File might have been deleted between listing and fetch
                    logger.info("Could not fetch %s (HTTP %d), skipping", f["name"], resp.status_code)
            except Exception as exc:
                logger.warning("Error fetching %s: %s", f["name"], exc)

    return {
        "items": items,
        "has_more": has_more,
        "next_filename": next_filename,
    }
