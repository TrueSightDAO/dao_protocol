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
