"""Design management endpoints for Agroverse white-label corporate gifting.

Handles upload, listing, image proxy, and order placement for custom
chocolate bar label designs stored in the agroverse-designs GitHub repo.

Requires DAO_PROTOCOL_GITHUB_PAT for all write operations.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import uuid
from typing import Optional

from PIL import Image
from fastapi import APIRouter, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from ..crypto import verify as verify_mod
from ..services import github_upload
from ..sheets import contributors_digital_signatures as cds
from ..sheets import design_events_log as delog

logger = logging.getLogger("dao_protocol.design")

router = APIRouter()

DESIGNS_OWNER = "TrueSightDAO"
DESIGNS_REPO = "agroverse-designs"
DESIGNS_BRANCH = "main"
REQUIRED_WIDTH_PX = 1200   # 4 inches at 300 DPI
REQUIRED_HEIGHT_PX = 600   # 2 inches at 300 DPI
ALLOWED_MIME = {"image/png", "image/jpeg"}

_DESIGN_ID_RE = re.compile(r"^[a-f0-9-]{36}$")


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.lower().strip().encode()).hexdigest()


def _verify_rsa_and_email(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Verify RSA signature and extract verified email from the payload.

    Returns (email, public_key, error_message).
    """
    try:
        result = verify_mod.verify(text)
    except verify_mod.VerificationError:
        return None, None, "Signature verification error"
    except Exception:
        return None, None, "Signature verification failed"

    if not result.get("success"):
        return None, None, "Invalid RSA signature"

    pk = result.get("public_key", "")
    entry = cds.find_by_public_key(pk) if pk else None
    if not entry or entry.get("status") != "ACTIVE":
        return None, None, "Public key not registered or not ACTIVE"

    email = entry.get("email", "")
    if not email:
        return None, None, "No email associated with this public key"

    return email, pk, None


def _extract_field(text: str, label: str) -> str:
    for line in text.split("\n"):
        if line.strip().startswith(f"- {label}:"):
            return line.split(":", 1)[1].strip()
    return ""


def _valid_image(file_bytes: bytes, filename: str) -> str | None:
    """Validate image dimensions and format. Returns error string or None."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("png", "jpg", "jpeg"):
        return f"Unsupported file type: .{ext}. Must be PNG or JPEG."
    try:
        img = Image.open(io.BytesIO(file_bytes))
        w, h = img.size
        if w != REQUIRED_WIDTH_PX or h != REQUIRED_HEIGHT_PX:
            return (
                f"Image must be exactly {REQUIRED_WIDTH_PX}x{REQUIRED_HEIGHT_PX}px "
                f'(4"x2" at 300 DPI). Got {w}x{h}px.'
            )
    except Exception as e:
        return f"Cannot read image: {e}"
    return None


@router.post("/design/upload")
async def design_upload(request: Request) -> JSONResponse:
    form = await request.form()
    text = str(form.get("text") or "").strip()
    attachment = form.get("attachment")

    email, _, error = _verify_rsa_and_email(text)
    if error:
        return JSONResponse({"status": "error", "error": error}, status_code=401)

    if attachment is None or not hasattr(attachment, "read"):
        return JSONResponse({"status": "error", "error": "No design file attached"}, status_code=400)

    design_id = _extract_field(text, "Design ID")
    if not _DESIGN_ID_RE.match(design_id):
        design_id = str(uuid.uuid4())

    filename = _extract_field(text, "Filename") or getattr(attachment, "filename", "design.png")
    file_bytes = await attachment.read()

    dims_error = _valid_image(file_bytes, filename)
    if dims_error:
        return JSONResponse({"status": "error", "error": dims_error}, status_code=422)

    if not delog.log_upload(email, design_id, filename, text):
        return JSONResponse({"status": "error", "error": "Design already uploaded (duplicate design_id)"}, status_code=409)

    eh = _email_hash(email)
    dir_path = f"designs/{eh}"

    if not github_upload.write_design_json(
        DESIGNS_OWNER, DESIGNS_REPO, DESIGNS_BRANCH,
        f"{dir_path}/{design_id}.json",
        {
            "design_id": design_id,
            "email_hash": eh,
            "filename": filename,
            "image_url": (f"https://raw.githubusercontent.com/{DESIGNS_OWNER}/{DESIGNS_REPO}"
                          f"/{DESIGNS_BRANCH}/{dir_path}/{design_id}.png"),
            "dimensions": "4x2in",
            "created_at": _extract_field(text, "Created At") or "",
            "orders": [],
        },
    ):
        return JSONResponse({"status": "error", "error": "Failed to write design JSON to GitHub"}, status_code=500)

    if not github_upload._put_file(
        github_upload.get_settings().github_pat,
        DESIGNS_OWNER, DESIGNS_REPO, DESIGNS_BRANCH,
        f"{dir_path}/{design_id}.png",
        file_bytes, filename, text,
    ):
        return JSONResponse({"status": "error", "error": "Failed to upload design image to GitHub"}, status_code=500)

    return JSONResponse({
        "status": "ok",
        "design_id": design_id,
        "image_url": (f"https://raw.githubusercontent.com/{DESIGNS_OWNER}/{DESIGNS_REPO}"
                      f"/{DESIGNS_BRANCH}/{dir_path}/{design_id}.png"),
    })


@router.get("/design/list")
async def design_list(
    request: Request,
    signed_payload: str = Query(...),
) -> JSONResponse:
    text = signed_payload
    email, _, error = _verify_rsa_and_email(text)
    if error:
        return JSONResponse({"status": "error", "error": error}, status_code=401)

    eh = _email_hash(email)
    dir_path = f"designs/{eh}"
    entries = github_upload.list_design_directory(DESIGNS_OWNER, DESIGNS_REPO, dir_path)
    if entries is None:
        return JSONResponse({"status": "ok", "designs": []})

    designs = []
    for entry in entries:
        if entry["name"].endswith(".json"):
            content = github_upload.get_file_content(DESIGNS_OWNER, DESIGNS_REPO, entry["path"])
            if content:
                try:
                    designs.append(json.loads(content.decode("utf-8")))
                except json.JSONDecodeError:
                    pass

    designs.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return JSONResponse({"status": "ok", "designs": designs})


@router.get("/design/image/{design_uuid}")
async def design_image(design_uuid: str, request: Request) -> Response:
    if not _DESIGN_ID_RE.match(design_uuid):
        return Response(status_code=400)

    email = request.query_params.get("email", "")
    if not email:
        return Response(status_code=400)

    eh = _email_hash(email)
    path = f"designs/{eh}/{design_uuid}.png"
    content = github_upload.get_file_content(DESIGNS_OWNER, DESIGNS_REPO, path)
    if content is None:
        return Response(status_code=404)

    return Response(content=content, media_type="image/png")


@router.post("/design/order")
async def design_order(request: Request) -> JSONResponse:
    form = await request.form()
    text = str(form.get("text") or "").strip()

    email, _, error = _verify_rsa_and_email(text)
    if error:
        return JSONResponse({"status": "error", "error": error}, status_code=401)

    design_id = _extract_field(text, "Design ID")
    quantity = _extract_field(text, "Quantity")
    unit_price = _extract_field(text, "Unit Price") or "10.00"
    sku = _extract_field(text, "SKU") or "custom-white-label-chocolate-bar-50g"

    if not design_id or not quantity:
        return JSONResponse({"status": "error", "error": "Design ID and Quantity are required"}, status_code=400)

    try:
        qt = int(quantity)
        if qt < 50:
            return JSONResponse({"status": "error", "error": "Minimum order quantity is 50"}, status_code=400)
    except ValueError:
        return JSONResponse({"status": "error", "error": "Invalid quantity"}, status_code=400)

    eh = _email_hash(email)
    json_path = f"designs/{eh}/{design_id}.json"
    order_id = str(uuid.uuid4())

    if not delog.log_order(email, design_id, order_id, quantity, text):
        return JSONResponse({"status": "error", "error": "Order already placed (duplicate order_id)"}, status_code=409)

    order_entry = {
        "order_id": order_id,
        "quantity": qt,
        "unit_price": float(unit_price),
        "sku": sku,
        "status": "pending",
        "created_at": "",
    }

    if not github_upload.append_order_to_design(
        DESIGNS_OWNER, DESIGNS_REPO, DESIGNS_BRANCH, json_path, order_entry,
    ):
        return JSONResponse({"status": "error", "error": "Failed to record order"}, status_code=500)

    design_content = github_upload.get_file_content(DESIGNS_OWNER, DESIGNS_REPO, json_path)
    design = json.loads(design_content.decode("utf-8")) if design_content else {}

    return JSONResponse({
        "status": "ok",
        "order_id": order_id,
        "design_id": design_id,
        "quantity": qt,
        "unit_price": float(unit_price),
        "sku": sku,
        "image_url": design.get("image_url", ""),
    })
