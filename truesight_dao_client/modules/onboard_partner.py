#!/usr/bin/env python3
"""Onboard a new partner end-to-end — ledger, inventory, and discovery surfaces.

Renamed 2026-04-30 from ``onboard_retail_partner`` and extended with a
``--role`` flag (``retail`` | ``processing`` | ``operator``) so the same
module handles retail venues (places that sell our cacao), processing
partners (facilities that *convert* nibs → bars / ship / store inventory),
and operator partners (people contributing operational/infra labor — AWS
admin, freight, ops support — who need a Contributors row + Agroverse
Partners row for follow-up tracking but no public partner page). Collapses
the manual steps in ``agentic_ai_context/RETAILER_TECHNICAL_ONBOARDING.md``
§3 into a single manifest-driven CLI invocation:

  Step 1.  Submit ``[CONTRIBUTOR ADD EVENT]`` for the partner contact, name
           pre-formatted as ``<First Name> - <Partner Name>``.
  Step 2.  Set ``Contributors contact information`` col **U** (Mailing
           Address). **Does not** set col T — that flag is reserved for
           online-fulfillment managers (Gary + Kirsten only).
  Step 3.  Append ``Agroverse Partners`` row with all required fields.
  Step 5.  Update website discovery surfaces in ``agroverse_shop_beta``:
           * ``js/partners-data.js`` (lat/lon + description for the
             partners-hub map and `/cacao-journeys/...` filters)
           * ``partner_locations.json``
           This step is skipped automatically when ``agroverse_shop`` clone
           isn't found, with a printed reminder.
  Step 13. Submit one ``[INVENTORY MOVEMENT]`` event per opening-order
           QR code (retail role only — processing partners typically
           receive inventory via a separate flow).
  Step 14. Run inventory + velocity syncs locally so the JSON snapshots
           in ``agroverse-inventory`` are fresh.

Still operator-handled (manual after the script finishes — printed
checklist at the end):
  - Step 4: geocoding (manifest must include ``lat`` / ``lon``)
  - Steps 6–10: partner-page HTML scaffold (``partners/<slug>/index.html``),
    hub card insert (``partners/index.html``), wholesale-list insert
    (``wholesale/index.html``), per-journey listing (e.g.
    ``cacao-journeys/pacific-west-coast-path/index.html``)
  - Step 11: photo upload to ``assets/partners/headers/`` etc.
  - Step 12 + 15: PR creation in ``agroverse_shop_beta`` and
    ``agroverse-inventory``

Why this scope: the *ledger* steps + the partners-data/locations json
files cause the most pain when forgotten (e.g. partner page lands on the
site but the new partner doesn't appear on the hub map — see PR #92 on
``agroverse_shop_beta``, where Shiok Kitchen had this exact gap). HTML
scaffolding (steps 6–10) remains operator-driven because the partner
page narrative + photo curation is too creative for a deterministic
template emitter. CI lint (separate follow-up) catches anything that
slips through the automation.

Idempotency: every step checks "is this already done?" before acting.
Re-running the same manifest is safe.

Usage:
    cd dao_client
    python -m truesight_dao_client.modules.onboard_partner \\
        --manifest path/to/manifest.yaml --role retail --dry-run
    python -m truesight_dao_client.modules.onboard_partner \\
        --manifest path/to/manifest.yaml --role processing --execute

Manifest schema (YAML):
    partner_id: shiok-kitchen-menlo-park       # slug; canonical key (required for retail/processing; omit for operator)
    partner_name: Shiok Singapore Kitchen      # for operator role: the partner-org name (e.g. "UX.APP")
    contact_first_name: Dennis
    email: shiokkitchen@gmail.com
    address: "625 Oak Grove Avenue, Menlo Park, CA 94025"   # required for retail/processing; optional for operator
    location: "Menlo Park, California"         # used for Agroverse Partners col F + journey filter (omit for operator)
    role: processing                            # retail | processing | operator — overridable via CLI --role
    partner_type: Manufacturer                  # Wholesale / Consignment / Operator / Supplier / Manufacturer (defaults to Operator when role=operator)
    partner_type_label:                         # optional; narrative shown on the partner page
       "Processing Partner — Commercial Kitchen Access (Off-Hours)"
    lat: 37.4527                                # required for js/partners-data.js
    lon: -122.1838                              # required for js/partners-data.js
    description: "27-year family-run Singaporean restaurant…"   # required for partners-data.js + hub
    notes: ""                                   # optional; col G
    opening_order:                              # optional (retail role); omit to skip step 13
      source_manager: "Kirsten Ritschel"
      inventory_item: "<full Currency string from Agroverse QR codes col I>"
      qr_codes:
        - 2024OSCAR_20260330_23
    run_syncs: true                             # default true; runs sync_*.py if available
    agroverse_shop_path: "../agroverse_shop"    # optional; defaults to ../agroverse_shop sibling

Requires:
- dao_client ``.env`` (signing identity for Edgar) — same as other modules.
- A ``google_credentials.json`` with editor access to the Main Ledger
  (``1GE7PUq-…``). Searched in this order:
    1. ``$DAO_CLIENT_GOOGLE_CREDENTIALS`` env var
    2. ``dao_client/google_credentials.json``
    3. ``../market_research/google_credentials.json``
- ``gspread`` and ``google-auth`` installed (see requirements.txt of the
  market_research repo or install: ``pip install gspread google-auth``).
- (Optional, for step 14) a sibling clone of
  ``TrueSightDAO/go_to_market`` checked out at ``../market_research`` so
  the inventory + velocity sync scripts can be invoked.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

from ..edgar_client import EdgarClient

MAIN_LEDGER_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
PARTNERS_SHEET = "Agroverse Partners"
CONTRIBUTORS_SHEET = "Contributors contact information"

# Contributors column indices (1-based for gspread cell ops).
CCI_COL_NAME = 1   # A
CCI_COL_EMAIL = 4  # D
CCI_COL_T_STORE_MGR = 20  # T — DO NOT SET TRUE for retail partners
CCI_COL_U_MAILING = 21    # U — set this with the address

ALLOWED_PARTNER_TYPES = {"Wholesale", "Consignment", "Operator", "Supplier", "Manufacturer"}

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Manifest loading + validation
# ---------------------------------------------------------------------------

@dataclass
class OpeningOrder:
    source_manager: str
    inventory_item: str
    qr_codes: list[str] = field(default_factory=list)


VALID_ROLES = {"retail", "processing", "operator"}

# Roles that anchor to a physical venue and therefore require address/location
# for downstream steps (mailing-address write, partners-data.js geocoding,
# inventory movements). ``operator`` partners are people, not places — they
# only need the contributor row + Agroverse Partners follow-up entry.
VENUE_ROLES = {"retail", "processing"}


@dataclass
class Manifest:
    partner_id: str
    partner_name: str
    contact_first_name: str
    email: str
    address: str
    location: str
    partner_type: str = "Consignment"
    role: str = "retail"
    partner_type_label: str = ""  # narrative shown on the partner page; default derives from role
    lat: float | None = None
    lon: float | None = None
    description: str = ""
    notes: str = ""
    opening_order: OpeningOrder | None = None
    run_syncs: bool = True
    agroverse_shop_path: str | None = None

    @property
    def contributor_full_name(self) -> str:
        """Canonical partner contact name: ``<First> - <Partner Name>``.

        Pre-formatting prevents Edgar's auto-rename from breaking the
        ``Agroverse Partners.E`` ↔ ``Contributors.A`` join. See
        ``RETAILER_TECHNICAL_ONBOARDING.md`` §3.1 + §6a.
        """
        return f"{self.contact_first_name.strip()} - {self.partner_name.strip()}"

    @property
    def partner_page_url(self) -> str:
        # Operator partners don't have public partner pages; the existing
        # Agroverse Partners rows for Operator type (e.g. "Gary Teh") have
        # empty col C, so mirror that.
        if self.role == "operator" or not self.partner_id:
            return ""
        return f"https://agroverse.shop/partners/{self.partner_id}"

    @property
    def effective_partner_type_label(self) -> str:
        """Narrative label for the website Partner Type info-row.

        Defaults are deliberately simple — operators should override
        ``partner_type_label`` in the manifest with a more specific
        suffix (e.g. ``"Processing Partner — Commercial Kitchen Access (Off-Hours)"``).
        """
        if self.partner_type_label.strip():
            return self.partner_type_label.strip()
        if self.role == "operator":
            return "Operator Partner"
        return "Processing Partner" if self.role == "processing" else "Retail Partner"


def load_manifest(path: Path) -> Manifest:
    if yaml is None:
        raise SystemExit("PyYAML is required: pip install pyyaml")
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise SystemExit(f"Manifest must be a YAML mapping (got {type(raw).__name__}).")

    role = (raw.get("role") or "retail").strip().lower()
    if role not in VALID_ROLES:
        raise SystemExit(f"role must be one of {sorted(VALID_ROLES)}; got {role!r}.")

    # Operator partners don't anchor to a venue; only the contributor identity
    # fields are required. Venue roles (retail/processing) still need address
    # + location so downstream steps (mailing-address write, partners-data.js,
    # journey filters) can run.
    if role in VENUE_ROLES:
        required = ["partner_id", "partner_name", "contact_first_name", "email", "address", "location"]
    else:
        required = ["partner_name", "contact_first_name", "email"]
    missing = [k for k in required if not raw.get(k)]
    if missing:
        raise SystemExit(f"Manifest missing required fields for role={role!r}: {', '.join(missing)}")

    default_ptype = "Operator" if role == "operator" else "Consignment"
    ptype = (raw.get("partner_type") or default_ptype).strip()
    if ptype not in ALLOWED_PARTNER_TYPES:
        raise SystemExit(
            f"partner_type must be one of {sorted(ALLOWED_PARTNER_TYPES)}; got {ptype!r}."
        )

    oo = None
    if raw.get("opening_order"):
        oo_raw = raw["opening_order"]
        for k in ("source_manager", "inventory_item", "qr_codes"):
            if not oo_raw.get(k):
                raise SystemExit(f"opening_order.{k} required when opening_order is provided")
        oo = OpeningOrder(
            source_manager=str(oo_raw["source_manager"]).strip(),
            inventory_item=str(oo_raw["inventory_item"]).strip(),
            qr_codes=[str(q).strip() for q in oo_raw["qr_codes"] if str(q).strip()],
        )

    lat = raw.get("lat")
    lon = raw.get("lon")
    try:
        lat_f = float(lat) if lat is not None else None
        lon_f = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        raise SystemExit(f"lat/lon must be numeric if provided; got lat={lat!r} lon={lon!r}.")

    return Manifest(
        partner_id=str(raw.get("partner_id") or "").strip(),
        partner_name=str(raw["partner_name"]).strip(),
        contact_first_name=str(raw["contact_first_name"]).strip(),
        email=str(raw["email"]).strip(),
        address=str(raw.get("address") or "").strip(),
        location=str(raw.get("location") or "").strip(),
        partner_type=ptype,
        role=role,
        partner_type_label=str(raw.get("partner_type_label") or "").strip(),
        lat=lat_f,
        lon=lon_f,
        description=str(raw.get("description") or "").strip(),
        notes=str(raw.get("notes") or "").strip(),
        opening_order=oo,
        run_syncs=bool(raw.get("run_syncs", True)),
        agroverse_shop_path=str(raw.get("agroverse_shop_path") or "").strip() or None,
    )


# ---------------------------------------------------------------------------
# Google Sheets helpers (gspread)
# ---------------------------------------------------------------------------

def _find_google_credentials() -> Path:
    env = os.environ.get("DAO_CLIENT_GOOGLE_CREDENTIALS")
    if env and Path(env).is_file():
        return Path(env)
    here = REPO_ROOT / "google_credentials.json"
    if here.is_file():
        return here
    sibling = REPO_ROOT.parent / "market_research" / "google_credentials.json"
    if sibling.is_file():
        return sibling
    raise SystemExit(
        "google_credentials.json not found. Set DAO_CLIENT_GOOGLE_CREDENTIALS, "
        "place it at dao_client/google_credentials.json, or have a sibling "
        "market_research/google_credentials.json checkout."
    )


def _gspread_client():
    try:
        import gspread  # type: ignore
        from google.oauth2.service_account import Credentials as SACreds  # type: ignore
    except ImportError as e:
        raise SystemExit(f"Missing dependency for sheet operations: {e}. pip install gspread google-auth")
    creds = SACreds.from_service_account_file(
        str(_find_google_credentials()),
        scopes=("https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.readonly"),
    )
    return gspread.authorize(creds)


def _retry(fn, *, attempts: int = 5, base_delay: float = 1.0):
    """Tiny retry for Sheets transient errors. Mirrors market_research helper."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(base_delay * (2 ** i))
    raise last  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Step 1: [CONTRIBUTOR ADD EVENT]
# ---------------------------------------------------------------------------

def _find_contributor_row(cci_data: list[list[str]], name: str) -> int | None:
    """Return 1-based row index for a Contributors row whose col A matches ``name``.

    Header row is at row 4 on this sheet (rows 1-3 are title + description),
    so iterate from row 5.
    """
    for i, row in enumerate(cci_data[4:], start=5):
        if row and row[0].strip().lower() == name.strip().lower():
            return i
    return None


def step1_contributor_add(client: EdgarClient, manifest: Manifest, *, dry_run: bool, verbose: bool) -> None:
    print("\n=== Step 1 — [CONTRIBUTOR ADD EVENT] ===")
    name = manifest.contributor_full_name
    print(f"  Contributor Name: {name!r}")
    print(f"  Contributor Email: {manifest.email!r}")

    # Idempotency: check if row already exists.
    gc = _gspread_client()
    sh = _retry(lambda: gc.open_by_key(MAIN_LEDGER_ID))
    cci = _retry(lambda: sh.worksheet(CONTRIBUTORS_SHEET))
    cci_data = _retry(lambda: cci.get_all_values())
    existing = _find_contributor_row(cci_data, name)
    if existing:
        print(f"  ✓ Already on sheet at row {existing}; skipping Edgar submit.")
        return

    if dry_run:
        print("  (dry-run) would submit [CONTRIBUTOR ADD EVENT] now.")
        return

    attributes = [
        ("Contributor Name", name),
        ("Contributor Email", manifest.email),
        ("Initial Digital Signature", "(none — store-manager contact, no key needed)"),
        ("Submitted At", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
        ("Submission Source", "dao_client/onboard_retail_partner"),
    ]
    resp = client.submit("CONTRIBUTOR ADD EVENT", attributes)
    if not resp.ok:
        raise SystemExit(f"Edgar [CONTRIBUTOR ADD EVENT] failed HTTP {resp.status_code}: {resp.text[:300]}")
    print(f"  ✓ HTTP {resp.status_code} — Edgar accepted; row will land within ~30s.")
    if verbose:
        print(f"    response: {resp.text[:200]}")


# ---------------------------------------------------------------------------
# Step 2: Contributors col U (Mailing Address) — explicitly NOT col T
# ---------------------------------------------------------------------------

def step2_set_mailing_address(manifest: Manifest, *, dry_run: bool, max_wait_s: int = 90) -> None:
    print("\n=== Step 2 — Contributors!U (Mailing Address) ===")
    if not manifest.address:
        print("  No address in manifest; skipping (typical for operator partners).")
        return
    print(f"  (col T 'Is Store Manager' intentionally NOT set — reserved for Gary + Kirsten only)")

    gc = _gspread_client()
    sh = _retry(lambda: gc.open_by_key(MAIN_LEDGER_ID))
    cci = _retry(lambda: sh.worksheet(CONTRIBUTORS_SHEET))

    # Wait for the row to land (step 1 is async via Edgar processing).
    name = manifest.contributor_full_name
    deadline = time.time() + max_wait_s
    row_idx: int | None = None
    while time.time() < deadline:
        cci_data = _retry(lambda: cci.get_all_values())
        row_idx = _find_contributor_row(cci_data, name)
        if row_idx:
            break
        if dry_run:
            break
        time.sleep(5)

    if not row_idx:
        if dry_run:
            print("  (dry-run) would wait for row + write col U with the address.")
            return
        raise SystemExit(
            f"Contributors row {name!r} did not land within {max_wait_s}s. "
            "Verify the [CONTRIBUTOR ADD EVENT] processed; re-run when present."
        )

    # Idempotency: only write if differs.
    current_u = ""
    cci_data = _retry(lambda: cci.get_all_values())
    if row_idx <= len(cci_data) and len(cci_data[row_idx - 1]) >= CCI_COL_U_MAILING:
        current_u = (cci_data[row_idx - 1][CCI_COL_U_MAILING - 1] or "").strip()
    if current_u == manifest.address:
        print(f"  ✓ Row {row_idx} col U already = {manifest.address!r}; skipping.")
        return

    if dry_run:
        print(f"  (dry-run) would write Contributors!U{row_idx} = {manifest.address!r}.")
        return

    _retry(lambda: cci.update_cell(row_idx, CCI_COL_U_MAILING, manifest.address))
    print(f"  ✓ Wrote Contributors!U{row_idx} = {manifest.address!r}.")


# ---------------------------------------------------------------------------
# Step 3: Append Agroverse Partners row
# ---------------------------------------------------------------------------

def step3_append_partners_row(manifest: Manifest, *, dry_run: bool) -> None:
    print("\n=== Step 3 — Append Agroverse Partners row ===")
    gc = _gspread_client()
    sh = _retry(lambda: gc.open_by_key(MAIN_LEDGER_ID))
    ap = _retry(lambda: sh.worksheet(PARTNERS_SHEET))
    ap_data = _retry(lambda: ap.get_all_values())

    # Idempotency: prefer partner_id (col A) when present; for operator rows
    # (no slug) fall back to contributor_contact_id (col E) match.
    contributor_id = manifest.contributor_full_name
    for r in ap_data[1:]:
        if not r:
            continue
        col_a = (r[0] if len(r) > 0 else "").strip()
        col_e = (r[4] if len(r) > 4 else "").strip()
        if manifest.partner_id and col_a == manifest.partner_id:
            print(f"  ✓ Row already exists for partner_id={manifest.partner_id!r}; skipping.")
            return
        if not manifest.partner_id and col_e and col_e.lower() == contributor_id.lower():
            print(f"  ✓ Row already exists for contributor={contributor_id!r}; skipping.")
            return

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_row = [
        manifest.partner_id,                   # A partner_id
        manifest.partner_name,                 # B partner_name
        manifest.partner_page_url,             # C partner_page_url
        "active",                              # D status
        manifest.contributor_full_name,        # E contributor_contact_id (MUST match Contributors.A)
        manifest.location,                     # F location
        manifest.notes,                        # G notes
        now_iso,                               # H last_synced_at
        manifest.partner_type,                 # I partner type
    ]
    print(f"  partner_id: {manifest.partner_id}")
    print(f"  contributor_contact_id (col E): {manifest.contributor_full_name!r}")
    print(f"  partner type (col I): {manifest.partner_type}")

    if dry_run:
        print("  (dry-run) would append the row.")
        return

    _retry(lambda: ap.append_row(new_row, value_input_option="USER_ENTERED"))
    print("  ✓ Appended.")


# ---------------------------------------------------------------------------
# Step 5: Update website discovery surfaces (js/partners-data.js + partner_locations.json)
# ---------------------------------------------------------------------------

def _resolve_agroverse_shop_path(manifest: Manifest) -> Path | None:
    """Locate the agroverse_shop clone. Manifest override > sibling default."""
    if manifest.agroverse_shop_path:
        p = Path(manifest.agroverse_shop_path).expanduser().resolve()
        return p if p.is_dir() else None
    sibling = REPO_ROOT.parent / "agroverse_shop"
    return sibling if sibling.is_dir() else None


def _update_partner_locations_json(shop_path: Path, manifest: Manifest, *, dry_run: bool) -> str:
    target = shop_path / "partner_locations.json"
    if not target.is_file():
        return f"  [skip] {target} not found"
    try:
        data = json.loads(target.read_text())
    except json.JSONDecodeError as e:
        return f"  [skip] {target.name}: invalid JSON ({e})"
    if manifest.partner_id in data:
        return f"  ✓ {target.name}: already has '{manifest.partner_id}' (idempotent skip)"
    if dry_run:
        return f"  (dry-run) would add '{manifest.partner_id}' to {target.name}"
    # Insert alphabetically by slug to keep diffs clean.
    entries = list(data.items())
    entries.append((manifest.partner_id, {"name": manifest.partner_name, "location": manifest.location}))
    entries.sort(key=lambda kv: kv[0])
    target.write_text(json.dumps(dict(entries), indent=2) + "\n", encoding="utf-8")
    return f"  ✓ wrote {target.name} with '{manifest.partner_id}'"


def _update_partners_data_js(shop_path: Path, manifest: Manifest, *, dry_run: bool) -> str:
    target = shop_path / "js" / "partners-data.js"
    if not target.is_file():
        return f"  [skip] {target} not found"
    if manifest.lat is None or manifest.lon is None:
        return f"  [skip] partners-data.js: manifest missing lat/lon"
    if not manifest.description:
        return f"  [skip] partners-data.js: manifest missing description"
    text = target.read_text(encoding="utf-8")
    needle = f"'{manifest.partner_id}':"
    if needle in text:
        return f"  ✓ partners-data.js: already has '{manifest.partner_id}' (idempotent skip)"
    if dry_run:
        return f"  (dry-run) would add '{manifest.partner_id}' entry to partners-data.js"

    # Escape single quotes for JS string literals.
    def js_str(s: str) -> str:
        return s.replace("\\", "\\\\").replace("'", "\\'")

    role_field = f",\n        partner_role: '{js_str(manifest.role)}'" if manifest.role != "retail" else ""
    block = (
        f"    '{js_str(manifest.partner_id)}': {{\n"
        f"        name: '{js_str(manifest.partner_name)}',\n"
        f"        slug: '{js_str(manifest.partner_id)}',\n"
        f"        lat: {manifest.lat},\n"
        f"        lon: {manifest.lon},\n"
        f"        location: '{js_str(manifest.location)}',\n"
        f"        description: '{js_str(manifest.description)}'"
        f"{role_field}\n"
        f"    }},\n"
    )

    # Insert just before the final `};` of the PARTNERS_DATA object.
    closer = "\n};"
    idx = text.rfind(closer)
    if idx < 0:
        return f"  [skip] partners-data.js: closing '\\n}};' not found"
    new_text = text[:idx] + "\n" + block.rstrip("\n") + text[idx:]
    target.write_text(new_text, encoding="utf-8")
    return f"  ✓ wrote partners-data.js with '{manifest.partner_id}'"


def step5_update_listings(manifest: Manifest, *, dry_run: bool) -> None:
    print("\n=== Step 5 — Website discovery surfaces (partner_locations.json + js/partners-data.js) ===")
    shop_path = _resolve_agroverse_shop_path(manifest)
    if shop_path is None:
        print("  [skip] No agroverse_shop clone found (set agroverse_shop_path in manifest "
              "or have a sibling ../agroverse_shop checkout). The operator must update "
              "partner_locations.json + js/partners-data.js manually before merging.")
        return
    print(f"  Target: {shop_path}")
    print(_update_partner_locations_json(shop_path, manifest, dry_run=dry_run))
    print(_update_partners_data_js(shop_path, manifest, dry_run=dry_run))


# ---------------------------------------------------------------------------
# Step 13: Inventory movement loop
# ---------------------------------------------------------------------------

def _movement_already_logged(qr_code: str, recipient: str, gc) -> bool:
    """Idempotency check — skip if Inventory Movement already has the QR row.

    Reads the Telegram & Submissions spreadsheet (1qbZZhf-…) Inventory
    Movement tab and looks for any row whose F column ('Contribution Made')
    contains both this QR code and this recipient.
    """
    try:
        tg = _retry(lambda: gc.open_by_key("1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"))
        ws = _retry(lambda: tg.worksheet("Inventory Movement"))
        rows = _retry(lambda: ws.get_all_values())
    except Exception:
        # If we can't read the dedup source, fall through and submit anyway.
        return False
    for row in rows[1:]:
        if not row:
            continue
        contribution = " ".join(row[:14]).lower()
        if qr_code.lower() in contribution and recipient.lower() in contribution:
            return True
    return False


def step13_submit_movements(client: EdgarClient, manifest: Manifest, *, dry_run: bool) -> None:
    print("\n=== Step 13 — [INVENTORY MOVEMENT] events ===")
    if not manifest.opening_order:
        print("  No opening_order in manifest; skipping.")
        return
    oo = manifest.opening_order
    recipient = manifest.contributor_full_name
    print(f"  Manager Name (sender): {oo.source_manager}")
    print(f"  Recipient Name: {recipient}")
    print(f"  Inventory Item: {oo.inventory_item[:60]}…")
    print(f"  QR codes: {len(oo.qr_codes)}")

    gc = _gspread_client()

    submitted = 0
    skipped = 0
    failed: list[tuple[str, str]] = []
    for qr in oo.qr_codes:
        if _movement_already_logged(qr, recipient, gc):
            print(f"  - {qr}: ✓ already logged; skip")
            skipped += 1
            continue
        if dry_run:
            print(f"  - {qr}: (dry-run) would submit")
            continue
        attrs = [
            ("Manager Name", oo.source_manager),
            ("Recipient Name", recipient),
            ("Inventory Item", oo.inventory_item),
            ("QR Code", qr),
            ("Quantity", "1"),
        ]
        resp = client.submit("INVENTORY MOVEMENT", attrs)
        if resp.ok:
            print(f"  - {qr}: HTTP {resp.status_code}")
            submitted += 1
        else:
            print(f"  - {qr}: HTTP {resp.status_code} — {resp.text[:120]}")
            failed.append((qr, f"HTTP {resp.status_code}"))
    print(f"\n  submitted={submitted} skipped={skipped} failed={len(failed)}")
    if failed:
        for qr, why in failed:
            print(f"    failed: {qr} ({why})")
        raise SystemExit("One or more movements failed; re-run after investigating.")


# ---------------------------------------------------------------------------
# Step 14: Run inventory + velocity syncs
# ---------------------------------------------------------------------------

def step14_run_syncs(*, dry_run: bool, market_research_path: Path | None = None) -> None:
    print("\n=== Step 14 — Run inventory + velocity syncs ===")
    mr = market_research_path or (REPO_ROOT.parent / "market_research")
    if not mr.is_dir():
        print(f"  Skipping: {mr} not a directory. Have a sibling clone of TrueSightDAO/go_to_market.")
        return
    inventory_script = mr / "scripts" / "sync_agroverse_store_inventory.py"
    velocity_script = mr / "scripts" / "sync_partners_velocity.py"

    for label, script in (("inventory", inventory_script), ("velocity", velocity_script)):
        if not script.is_file():
            print(f"  Skipping {label} sync: {script} missing.")
            continue
        if dry_run:
            print(f"  (dry-run) would run: python3 {script} --execute")
            continue
        print(f"  Running {label} sync…")
        result = subprocess.run(
            ["python3", str(script), "--execute"],
            cwd=str(mr),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            print(f"  ✗ {label} sync failed (rc={result.returncode}):")
            print(f"    stderr: {result.stderr[-500:]}")
            raise SystemExit(f"{label} sync failed; partners-{label}.json not refreshed.")
        # Print last 4 lines of stdout for confirmation.
        tail = "\n".join(result.stdout.strip().splitlines()[-4:])
        print(f"  ✓ {label} sync ok:\n{tail}")


# ---------------------------------------------------------------------------
# Manual-step instructions (printed at end)
# ---------------------------------------------------------------------------

_MANUAL_STEPS_TEMPLATE_RETAIL = """
=== Manual steps remaining (HTML scaffolding + photos) ===

The script handled: ledger ([CONTRIBUTOR ADD] / Contributors col U /
Agroverse Partners), website discovery surfaces (js/partners-data.js +
partner_locations.json), and (when applicable) opening-order
[INVENTORY MOVEMENT] events + inventory/velocity syncs.

Operator still owns:

1. partners/{slug}/index.html — partner page narrative.
   Clone partners/lumin-earth-apothecary/index.html and find-replace:
     - lumin-earth-apothecary  →  {slug}
     - Lumin Earth Apothecary  →  {name}
     - Morro Bay / 875 Main St → {address}
     - lat / lon coords         → {lat} / {lon}
     - Partner Type info-row    → "{type_label}"
   Then rewrite the about/mission paragraph (Lumin's is owner-specific).

2. partners/index.html — alphabetical card insert.
   Use Lumin Earth's card structure as template.

3. wholesale/index.html — alphabetical insert:
     <li><a href="../partners/{slug}/index.html">{name}</a><span class="city">{location_short}</span></li>

4. cacao-journeys/{{relevant-journey}}/index.html — if your hero is .jpeg
   (not .jpg), append '{slug}' to the imageExt conditional at the bottom.

5. assets/partners/headers/{slug}-header.<ext> — upload hero.
   assets/partners/logos/{slug}-logo.<ext>     — upload logo.

6. Open + merge PRs in agroverse_shop_beta and agroverse-inventory.

The full reference doc (with worked example):
  agentic_ai_context/RETAILER_TECHNICAL_ONBOARDING.md
"""

_MANUAL_STEPS_TEMPLATE_OPERATOR = """
=== Manual steps remaining (operator follow-up surface) ===

The script handled: ledger ([CONTRIBUTOR ADD] for {contributor!r} +
Agroverse Partners row with partner_type='Operator').

Operator partners are people, not venues — they have no public partner
page, no website surfaces, and receive no inventory. The remaining work
is relationship + tracking:

1. Confirm the contributor's preferred contact channel (email vs phone)
   and log it on the Contributors row if not already captured.

2. Add the partner to whatever follow-up cadence applies — partner
   check-ins, Slack/Telegram intros, or the Hit List equivalent for
   operator partners.

3. If the operator needs a digital signature (RSA key) to submit signed
   events on behalf of the DAO, walk them through
   https://dapp.truesight.me/create_signature.html and then run a
   [CONTRIBUTOR ADD EVENT] update with the public key (or
   ``python -m truesight_dao_client.modules.report_dapp_permission_change``
   if role changes are needed).

No HTML scaffolding, no inventory movement, no syncs. Re-running this
manifest is a no-op.
"""


_MANUAL_STEPS_TEMPLATE_PROCESSING = """
=== Manual steps remaining (HTML scaffolding + photos) ===

The script handled: ledger ([CONTRIBUTOR ADD] / Contributors col U /
Agroverse Partners) and website discovery surfaces (js/partners-data.js
+ partner_locations.json with `partner_role: 'processing'` tag).

Operator still owns:

1. partners/{slug}/index.html — partner page narrative.
   Clone partners/shiok-kitchen-menlo-park/index.html (canonical processing
   template) and find-replace:
     - shiok-kitchen-menlo-park → {slug}
     - Shiok Singapore Kitchen  → {name}
     - 625 Oak Grove Ave        → {address}
     - lat 37.4527, lon -122.1838 → {lat} / {lon}
     - Partner Type info-row     → "{type_label}"
     - "Off-hours commercial kitchen access" framing → role-specific copy
   Rewrite the partnership-story section to capture how this partner
   came on (origin story, owner background, deal terms — sans pricing
   per the public/operational separation).

2. partners/index.html — alphabetical card insert.
   Use Shiok Kitchen's card structure as template (uses header image
   in place of a separate logo).

3. cacao-journeys/{{relevant-journey}}/index.html — processing partners
   are typically EXCLUDED from journey lists (the journey is a retail
   tour). Add '{slug}' to the exclusion filter alongside the existing
   `the-ponderosa-slab-city` / `prism-percussions` / `shiok-kitchen-menlo-park`
   exclusions on each journey page that filters by location.

4. assets/partners/headers/{slug}-header.<ext> — upload hero.
   (Logo optional for processing partners; the hub card can use the
   header image directly.)

5. Optional: photos under assets/partners/{slug}/ for in-body
   partnership-story imagery (e.g., handshake / kitchen / facility shots).

6. NOT applicable to processing partners: wholesale/index.html (that's
   a where-to-buy list for retail venues only).

7. Pricing artifact: append the rate quote + agreement screenshot URL
   to "Agroverse Cacao Processing Cost" sheet
   (1GE7PUq-…/edit?gid=603759787). Pricing is INTENTIONALLY off the
   public partner page — it lives on the operational cost sheet.

8. Open + merge PRs in agroverse_shop_beta and agroverse-inventory.

The full reference doc (with worked example):
  agentic_ai_context/RETAILER_TECHNICAL_ONBOARDING.md
  agentic_ai_context/notes/claude_donation_mint_2026-04-30.md (visual
    proof / notarization upload pattern, applicable to the processing
    cost agreement screenshot)
"""


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(manifest: Manifest, *, dry_run: bool, verbose: bool) -> None:
    label = "DRY RUN" if dry_run else "EXECUTE"
    header_id = manifest.partner_id or manifest.contributor_full_name
    print(f"=== Onboarding {header_id} ({manifest.partner_name}) [{label}] ===")
    print(f"role:        {manifest.role}")
    print(f"contributor: {manifest.contributor_full_name}")
    print(f"address:     {manifest.address or '(none — non-venue role)'}")
    print(f"location:    {manifest.location or '(none — non-venue role)'}")
    print(f"type:        {manifest.partner_type}")

    client = EdgarClient.from_env(generation_source="dao_client/onboard_partner")
    step1_contributor_add(client, manifest, dry_run=dry_run, verbose=verbose)
    step2_set_mailing_address(manifest, dry_run=dry_run)
    step3_append_partners_row(manifest, dry_run=dry_run)
    if manifest.role in VENUE_ROLES:
        step5_update_listings(manifest, dry_run=dry_run)
    else:
        print("\n=== Step 5 — Website discovery surfaces ===")
        print(f"  Skipping for role={manifest.role!r} (no public partner page).")

    if manifest.role == "retail":
        step13_submit_movements(client, manifest, dry_run=dry_run)
    elif manifest.role == "processing" and manifest.opening_order:
        # A processing manifest with an opening_order is unusual but valid —
        # e.g. an initial inbound shipment of cacao nibs to Dennis. Run it
        # but flag the unusual shape.
        print("\n=== Step 13 — opening_order on a processing role (unusual but supported) ===")
        step13_submit_movements(client, manifest, dry_run=dry_run)
    elif manifest.role == "operator":
        print("\n=== Step 13 — [INVENTORY MOVEMENT] events ===")
        print("  Skipping for role='operator' (operator partners receive no inventory).")

    if manifest.run_syncs and manifest.role in VENUE_ROLES:
        step14_run_syncs(dry_run=dry_run)
    elif manifest.role == "operator":
        print("\n=== Step 14 — Run inventory + velocity syncs ===")
        print("  Skipping for role='operator' (no inventory impact).")

    if manifest.role == "operator":
        template = _MANUAL_STEPS_TEMPLATE_OPERATOR
    elif manifest.role == "processing":
        template = _MANUAL_STEPS_TEMPLATE_PROCESSING
    else:
        template = _MANUAL_STEPS_TEMPLATE_RETAIL
    location_short = ", ".join(p.strip() for p in (manifest.location or "").split(",")[:2])
    print(template.format(
        slug=manifest.partner_id,
        name=manifest.partner_name,
        location=manifest.location,
        location_short=location_short,
        address=manifest.address,
        lat=manifest.lat if manifest.lat is not None else "<operator-supplied>",
        lon=manifest.lon if manifest.lon is not None else "<operator-supplied>",
        type_label=manifest.effective_partner_type_label,
        contributor=manifest.contributor_full_name,
        email=manifest.email,
    ))


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Onboard a partner end-to-end (retail or processing role)."
    )
    p.add_argument("--manifest", type=Path, required=True, help="Path to YAML manifest.")
    p.add_argument(
        "--role",
        choices=sorted(VALID_ROLES),
        default=None,
        help="Override the manifest's role field (retail | processing | operator). "
             "If omitted, the manifest's value is used (default: retail).",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True,
                   help="Print intended actions without side effects (default).")
    g.add_argument("--execute", action="store_true",
                   help="Perform side effects (Edgar submits, sheet writes, sync runs).")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(list(argv) if argv is not None else None)

    if not args.manifest.is_file():
        raise SystemExit(f"Manifest not found: {args.manifest}")
    manifest = load_manifest(args.manifest)
    if args.role:  # CLI override wins over manifest
        manifest.role = args.role
    run(manifest, dry_run=not args.execute, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
