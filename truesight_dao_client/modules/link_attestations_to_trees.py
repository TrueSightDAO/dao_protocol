#!/usr/bin/env python3
"""Link attested credentialing-cohort members to tree QR codes (mint-only).

Reusable across credentialing programs. For each **attested** roster row that
does not yet have a tree, mint one serialized tree-planting pledge QR via the
existing signed ``[DONATION MINT EVENT]`` flow (`mint_donation`), with:

  - ``qr_code``      == the member's credential ``pk_hash``      (binds the QR row
                        to ``truesight.me/programs/<slug>/credentials/#<pk_hash>``)
  - ``landing_page`` == the member's ``profile_url``            (scanning the tree
                        resolves to their certificate page)
  - ``currency`` / ledger / origin per the program **manifest**.

Then annotate the roster (``tree_qr_code`` + ``tree_issued_at``) and append a
``tree_issued`` row to the program's ``Audit Trail`` tab.

**Mint-only.** Trees land ``MINTED``; the operator marks them ``SOLD`` separately
(``report_sales`` / ``update_qr_code``). The ``tree_qr_code`` annotation is the
idempotency marker — a re-run only mints for newly-attested members, so this is
safe to run on a schedule (the first run backfills the existing cohort).

Design + rationale: ``agentic_ai_context/ERA_COHORT_TREE_ISSUANCE_PLAN.md``.

Usage (dry-run is the default):

    cd ~/Applications/dao_client && source .venv/bin/activate
    python -m truesight_dao_client.modules.link_attestations_to_trees \\
        --manifest truesight_dao_client/examples/attestation-trees/butterfly-effect.yaml
    # review, then:
    python -m truesight_dao_client.modules.link_attestations_to_trees \\
        --manifest .../butterfly-effect.yaml --execute
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import mint_donation

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None


# ── Manifest ────────────────────────────────────────────────────────────────

# Default roster column header → internal field. Overridable per manifest.
_DEFAULT_COLUMNS = {
    "name": "Name",
    "pk_hash": "pk_hash",
    "profile_url": "profile_url",
    "status": "status",
    "attestation_tx_id": "attestation_tx_id",
}
_TREE_QR_HEADER = "tree_qr_code"
_TREE_AT_HEADER = "tree_issued_at"


@dataclass
class Manifest:
    program_slug: str
    roster_sheet_id: str
    sa_credentials: str
    currency: str
    proof_file: str
    roster_tab: str = "Cohort Roster"
    audit_tab: str = "Audit Trail"
    price: float = 1.0
    attested_status: str = "processed"
    columns: dict = field(default_factory=lambda: dict(_DEFAULT_COLUMNS))


def load_manifest(path: Path) -> Manifest:
    if yaml is None:
        raise SystemExit("PyYAML is required: pip install pyyaml")
    raw = yaml.safe_load(path.read_text()) or {}
    cols = dict(_DEFAULT_COLUMNS)
    cols.update(raw.get("columns") or {})
    try:
        m = Manifest(
            program_slug=raw["program_slug"],
            roster_sheet_id=raw["roster_sheet_id"],
            sa_credentials=raw["sa_credentials"],
            currency=raw["currency"],
            proof_file=raw["proof_file"],
            roster_tab=raw.get("roster_tab", "Cohort Roster"),
            audit_tab=raw.get("audit_tab", "Audit Trail"),
            price=float(raw.get("price", 1)),
            attested_status=str(raw.get("attested_status", "processed")),
            columns=cols,
        )
    except KeyError as exc:
        raise SystemExit(f"manifest missing required key: {exc}")
    return m


# ── Sheets ──────────────────────────────────────────────────────────────────

def _open_roster(manifest: Manifest, base_dir: Path):
    try:
        import gspread  # type: ignore
        from google.oauth2.service_account import Credentials  # type: ignore
    except ImportError:
        raise SystemExit("gspread + google-auth required: pip install gspread google-auth")
    cred_path = Path(manifest.sa_credentials).expanduser()
    if not cred_path.is_absolute():
        cred_path = (base_dir / cred_path).resolve()
    if not cred_path.is_file():
        raise SystemExit(f"sa_credentials not found: {cred_path}")
    creds = Credentials.from_service_account_file(
        str(cred_path),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(manifest.roster_sheet_id)


def _col_letter(idx0: int) -> str:
    """0-based column index → A1 letter."""
    s, n = "", idx0 + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# ── Core ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(manifest: Manifest, *, manifest_dir: Path, execute: bool, limit: int | None) -> int:
    ss = _open_roster(manifest, manifest_dir)
    ws = ss.worksheet(manifest.roster_tab)
    rows = ws.get_all_values()
    if not rows:
        print("Roster is empty.")
        return 0
    header = [h.strip() for h in rows[0]]

    def col_idx(field_name: str) -> int:
        label = manifest.columns[field_name]
        if label not in header:
            raise SystemExit(f"roster missing column {label!r} (for {field_name})")
        return header.index(label)

    i_name = col_idx("name")
    i_pk = col_idx("pk_hash")
    i_profile = col_idx("profile_url")
    i_status = col_idx("status")
    i_att = col_idx("attestation_tx_id")

    # Ensure annotation columns exist (append at end if missing).
    def ensure_col(label: str) -> int:
        nonlocal header
        if label in header:
            return header.index(label)
        new_idx = len(header)
        if execute:
            ws.update_cell(1, new_idx + 1, label)
        header = header + [label]
        print(f"  + added roster column {label!r} at {_col_letter(new_idx)}")
        return new_idx

    i_tree = ensure_col(_TREE_QR_HEADER)
    i_tree_at = ensure_col(_TREE_AT_HEADER)

    proof_path = Path(manifest.proof_file).expanduser()
    if not proof_path.is_file():
        raise SystemExit(f"proof_file not found: {proof_path}")

    minted = skipped_done = skipped_ineligible = failed = 0
    audit_appends: list[list[str]] = []

    for r, row in enumerate(rows[1:], start=2):
        def cell(i: int) -> str:
            return (row[i].strip() if len(row) > i else "")

        name = cell(i_name)
        pk = cell(i_pk)
        profile = cell(i_profile)
        status = cell(i_status)
        att = cell(i_att)
        already = cell(i_tree) if i_tree < len(row) else ""

        if already:
            skipped_done += 1
            continue
        eligible = (status == manifest.attested_status) and bool(att) and bool(pk)
        if not eligible:
            skipped_ineligible += 1
            reason = "no pk_hash" if not pk else (f"status!={manifest.attested_status}" if status != manifest.attested_status else "no attestation_tx_id")
            print(f"  row {r}: SKIP {name or '(no name)'} — {reason}")
            continue

        argv = [
            "--qr-code", pk,
            "--currency", manifest.currency,
            "--donor-name", name or pk,
            "--donation-amount", f"{manifest.price:g}",
            "--proof-file", str(proof_path),
        ]
        if profile:
            argv += ["--landing-page", profile]

        if not execute:
            print(f"  row {r}: (dry-run) mint tree for {name!r} qr={pk} landing={profile or '(currency default)'}")
            minted += 1
            continue

        print(f"  row {r}: minting tree for {name!r} (qr={pk})…")
        try:
            rc = mint_donation.main(argv)
        except SystemExit as exc:  # argparse/proof errors inside mint_donation
            rc = int(exc.code) if isinstance(exc.code, int) else 1
        except Exception as exc:  # pragma: no cover
            print(f"    ✗ mint raised: {exc}")
            rc = 1
        if rc != 0:
            failed += 1
            print(f"    ✗ mint failed (rc={rc}) — leaving row unannotated for retry")
            continue

        ts = _now_iso()
        ws.update_cell(r, i_tree + 1, pk)
        ws.update_cell(r, i_tree_at + 1, ts)
        audit_appends.append([ts, name, "tree_issued", "", profile, "", "", "", pk])
        minted += 1
        print(f"    ✓ minted + annotated (tree_qr_code={pk})")

    # Append Audit Trail rows in one batch.
    if execute and audit_appends:
        try:
            audit_ws = ss.worksheet(manifest.audit_tab)
            audit_ws.append_rows(audit_appends, value_input_option="RAW")
            print(f"  appended {len(audit_appends)} '{manifest.audit_tab}' tree_issued row(s)")
        except Exception as exc:  # pragma: no cover
            print(f"  ! Audit Trail append failed (roster annotations still written): {exc}")

    mode = "EXECUTE" if execute else "DRY-RUN"
    print(
        f"\n[{mode}] program={manifest.program_slug} minted={minted} "
        f"already_done={skipped_done} ineligible={skipped_ineligible} failed={failed}"
    )
    if not execute:
        print("Re-run with --execute to mint.")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Mint one tree QR per attested credentialing-cohort member (mint-only; "
            "idempotent on tree_qr_code). Reuses [DONATION MINT EVENT] via mint_donation."
        ),
    )
    parser.add_argument("--manifest", required=True, help="Path to the program manifest YAML.")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--execute", action="store_true", help="Apply changes (default is dry-run).")
    g.add_argument("--dry-run", action="store_true", help="Preview only (default).")
    parser.add_argument("--limit", type=int, default=None, help="(reserved) cap rows processed.")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest).expanduser().resolve()
    if not manifest_path.is_file():
        parser.error(f"--manifest not found: {manifest_path}")
    manifest = load_manifest(manifest_path)
    return run(manifest, manifest_dir=manifest_path.parent, execute=args.execute, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())
