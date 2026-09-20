#!/usr/bin/env python3
"""Batch-allocate sold-but-unlinked QR codes to SunMint tree/plot links (plan PR7).

Unit PR7 of ``agentic_ai_context/plans/SUNMINT_FARMER_SETTLEMENT_AND_BATCH_LINK_PLAN.md``.

Today ~520 QRs sit `SOLD` with no tree ever linked, because linking is a manual
one-event-per-QR act. This tool computes the whole pairing in one pass and then
drives the existing `[TREE PLANTING LINK EVENT]` once per pair.

**Allocation rule (plan Decision 0.5)** — this is the whole point of the tool:

  * a **distinct, not-yet-used Owner Email** -> a specific *photographed tree*
    (a `SunMint Tree Planting` submission row, 1:1) + the existing owner email;
  * a **repeat email** (same address already allocated one tree in this run) or a
    **blank email** -> a **plot-level** association instead (plan PR6; a plot is a
    whole farm area, so it absorbs any number of un-photographed bags 1:1).

The target identity is resolved server-side from the registry (PR6's rule): for a
plot link the *farmer* comes from `SunMint Plots` column T, never from this
payload. This tool only chooses *which* registry row to point at.

**Dry-run is the default.** `--execute` (which additionally requires `--yes`)
submits the link events — and a link event books ledger rows, so live execution is
the plan's always-stop **ledger-money gate** (SS2): a governor must be present and
say go. Nothing here moves money on its own.

Data sources (all read-only here; all on Gary's `1qbZZhf...` sheet unless noted):

  * `Agroverse QR codes`      (main ledger `1GE7PUq...`) — the SOLD-unlinked QRs
  * `SunMint Tree Planting`   — eligible *photographed tree* units
  * `SunMint Plots`           — eligible plot targets + their `Contributor Name`

Usage::

    cd ~/Applications/dao_client && source .venv/bin/activate

    # 1. dry-run (default) — prints the plan + the exact events, submits nothing
    python -m truesight_dao_client.modules.batch_link_sunmint

    # 2. inspect, then live (ledger-money gate — governor present):
    python -m truesight_dao_client.modules.batch_link_sunmint --execute --yes
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# -- Spreadsheets -------------------------------------------------------------

SOURCE_SHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
MAIN_LEDGER_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"

QR_SHEET = "Agroverse QR codes"
SUNMINT_TAB = "SunMint Tree Planting"
PLOTS_TAB = "SunMint Plots"

EVENT_TAG = "TREE PLANTING LINK EVENT"
SUBMISSION_SOURCE = "batch_link_sunmint (PR7)"

# Column indices — 0-based, matching the GAS handler's own constants (verified
# 2026-09-20; see tokenomics/SCHEMA.md and process_tree_planting_link.js).
QR_CODE_COL = 0  # A  qr_code
QR_STATUS_COL = 3  # D  status
QR_OWNER_EMAIL_COL = 11  # L  Owner Email
QR_SOLD_DATE_COL = 26  # AA Sold Date
QR_LINKED_PLOT_COL = 28  # AC Linked Plot ID

SM_MESSAGE_ID_COL = 3  # D  Telegram Message ID (stable key)
SM_PHOTO_COL = 8  # I  Photo of Tree Planted
SM_CONTRIBUTOR_COL = 9  # J  Contributor Name (the farmer; the match key)
SM_STATUS_COL = 12  # M  Status
SM_LINKED_QR_COL = 17  # R  Linked QR Code (presence == already linked)

PLOT_ID_COL = 0  # A  Plot ID
PLOT_CONTRIBUTOR_COL = 19  # T  Contributor Name (registry-held farmer identity)

# QR statuses that mean "sold but not yet linked to a tree/plot".
LINKABLE_QR_STATUSES = {"SOLD", "TREE_PLANTING_FUNDS_TRANSFERRED"}
# SunMint submission status that means "confirmed, awaiting a link".
ELIGIBLE_SUBMISSION_STATUS = "NEW"


# -- Model --------------------------------------------------------------------


@dataclass(frozen=True)
class SoldQr:
    """A sold QR code awaiting a tree/plot link."""

    qr_code: str
    owner_email: str = ""
    sold_date: str = ""


@dataclass(frozen=True)
class TreeUnit:
    """A confirmed, photographed tree submission available for a 1:1 link."""

    submission_message_id: str
    contributor_name: str = ""


@dataclass(frozen=True)
class Plot:
    """A plot-registry row available for a plot-level association."""

    plot_id: str
    contributor_name: str = ""


@dataclass(frozen=True)
class Pairing:
    """One QR -> target allocation, plus *why* (the audit trail)."""

    qr_code: str
    owner_email: str
    kind: str  # "tree" | "plot"
    target_id: str  # submission_message_id (tree) or plot_id (plot)
    contributor_name: str
    reason: str


# -- Pure allocation core -----------------------------------------------------


def _norm_email(email: str | None) -> str:
    return (email or "").strip().lower()


def compute_allocations(
    qrs: Sequence[SoldQr],
    tree_units: Sequence[TreeUnit],
    plots: Sequence[Plot],
    available_units: int | None = None,
) -> tuple[list[Pairing], list[SoldQr]]:
    """Pair SOLD-unlinked QRs with tree/plot targets per Decision 0.5.

    Deterministic: QRs are ordered by (sold_date, qr_code) so a dry-run is
    reproducible and reviewable. Tree units and plots are consumed in the order
    supplied by the caller (which sorts them stably).

    Returns ``(pairings, unallocated)`` — QRs left over because every target was
    consumed, or because ``available_units`` capped the run. A QR with a distinct
    email but no tree unit left falls back to a plot (still a valid 1:1 link),
    and is only left unallocated when no plot is left either.
    """
    ordered = sorted(qrs, key=lambda q: (q.sold_date or "", q.qr_code))
    used_emails: set[str] = set()
    ti = 0  # next unused *tree* (1:1 -- each photographed tree is consumed once)
    pi = 0  # plot cursor; plots are REUSABLE, so we cycle round-robin
    pairings: list[Pairing] = []
    unallocated: list[SoldQr] = []

    for qr in ordered:
        if available_units is not None and len(pairings) >= available_units:
            unallocated.append(qr)
            continue

        email = _norm_email(qr.owner_email)

        # Decision 0.5a: a distinct, not-yet-used owner email claims a specific
        # photographed tree, 1:1. (Falls through to a plot when no tree is left.)
        if email and email not in used_emails and ti < len(tree_units):
            unit = tree_units[ti]
            ti += 1
            used_emails.add(email)
            pairings.append(
                Pairing(
                    qr_code=qr.qr_code,
                    owner_email=qr.owner_email.strip(),
                    kind="tree",
                    target_id=unit.submission_message_id,
                    contributor_name=unit.contributor_name,
                    reason="distinct owner email -> photographed tree (1:1)",
                )
            )
            continue

        # Decision 0.5b: a repeat email (already claimed a tree) or a blank email
        # takes a plot association. A plot spans many trees' worth of supply, so it
        # is reusable -- we cycle round-robin across the eligible plots.
        if plots:
            plot = plots[pi % len(plots)]
            pi += 1
            if email and email in used_emails:
                reason = "repeat owner email -> plot association"
            elif not email:
                reason = "no owner email -> plot association"
            else:
                reason = "no tree unit available -> plot association"
            pairings.append(
                Pairing(
                    qr_code=qr.qr_code,
                    owner_email=qr.owner_email.strip(),
                    kind="plot",
                    target_id=plot.plot_id,
                    contributor_name=plot.contributor_name,
                    reason=reason,
                )
            )
            continue

        # No tree and no plot left for this QR.
        unallocated.append(qr)

    return pairings, unallocated


def build_link_attributes(pairing: Pairing, updated_by: str) -> dict[str, str]:
    """Build the `[TREE PLANTING LINK EVENT]` attributes for one pairing.

    Exactly one of `SunMint Submission Message ID` (tree) / `Plot ID` (plot) is
    emitted — the GAS parser accepts either and rejects neither-present.
    """
    attrs: dict[str, str] = {"QR Code": pairing.qr_code}
    if pairing.kind == "tree":
        attrs["SunMint Submission Message ID"] = pairing.target_id
    elif pairing.kind == "plot":
        attrs["Plot ID"] = pairing.target_id
    else:  # pragma: no cover - guarded by the dataclass' producer
        raise ValueError(f"unknown pairing kind: {pairing.kind!r}")
    attrs["Updated by"] = updated_by
    attrs["Submission Source"] = SUBMISSION_SOURCE
    return attrs


# -- Sheet adapters (network) -------------------------------------------------


def _find_google_credentials():
    import os
    from pathlib import Path

    env = os.environ.get("DAO_CLIENT_GOOGLE_CREDENTIALS")
    if env and Path(env).is_file():
        return Path(env)
    here = Path(__file__).resolve().parents[2] / "google_credentials.json"
    if here.is_file():
        return here
    sibling = (
        Path(__file__).resolve().parents[2].parent
        / "market_research"
        / "google_credentials.json"
    )
    if sibling.is_file():
        return sibling
    raise SystemExit(
        "google_credentials.json not found. Set DAO_CLIENT_GOOGLE_CREDENTIALS, "
        "place it at dao_client/google_credentials.json, or have a sibling "
        "market_research/google_credentials.json."
    )


def _gspread_client():
    try:
        import gspread  # type: ignore
        from google.oauth2.service_account import Credentials  # type: ignore
    except ImportError:  # pragma: no cover
        raise SystemExit(
            "gspread + google-auth required: pip install gspread google-auth"
        )
    creds = Credentials.from_service_account_file(
        str(_find_google_credentials()),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    return gspread.authorize(creds)


def _cell(row: Sequence, idx: int) -> str:
    return str(row[idx]).strip() if idx < len(row) and row[idx] is not None else ""


def load_sold_unlinked_qrs(gc) -> list[SoldQr]:
    """SOLD (or funds-transferred) QR rows with no tree/plot link yet."""
    sh = gc.open_by_key(MAIN_LEDGER_ID).worksheet(QR_SHEET)
    out: list[SoldQr] = []
    for row in sh.get_all_values()[1:]:
        status = _cell(row, QR_STATUS_COL).upper()
        if status not in LINKABLE_QR_STATUSES:
            continue
        if _cell(row, QR_LINKED_PLOT_COL):
            continue  # already plot-linked
        qr_code = _cell(row, QR_CODE_COL)
        if not qr_code:
            continue
        out.append(
            SoldQr(
                qr_code=qr_code,
                owner_email=_cell(row, QR_OWNER_EMAIL_COL),
                sold_date=_cell(row, QR_SOLD_DATE_COL),
            )
        )
    return out


def load_tree_units(gc) -> list[TreeUnit]:
    """Confirmed, photographed, not-yet-linked SunMint submissions."""
    sh = gc.open_by_key(SOURCE_SHEET_ID).worksheet(SUNMINT_TAB)
    out: list[TreeUnit] = []
    for row in sh.get_all_values()[1:]:
        if _cell(row, SM_STATUS_COL).upper() != ELIGIBLE_SUBMISSION_STATUS:
            continue
        if _cell(row, SM_LINKED_QR_COL):
            continue  # already linked (idempotency marker)
        if not _cell(row, SM_PHOTO_COL):
            continue  # Decision 0.5 targets a *photographed* tree
        msg_id = _cell(row, SM_MESSAGE_ID_COL)
        if not msg_id:
            continue
        out.append(
            TreeUnit(
                submission_message_id=msg_id,
                contributor_name=_cell(row, SM_CONTRIBUTOR_COL),
            )
        )
    out.sort(key=lambda u: u.submission_message_id)
    return out


def load_plots(gc) -> list[Plot]:
    """Plot-registry rows that carry a registered farmer identity (fail closed)."""
    sh = gc.open_by_key(SOURCE_SHEET_ID).worksheet(PLOTS_TAB)
    out: list[Plot] = []
    for row in sh.get_all_values()[1:]:
        plot_id = _cell(row, PLOT_ID_COL)
        contributor = _cell(row, PLOT_CONTRIBUTOR_COL)  # col T, registry-held
        if not plot_id or not contributor:
            continue  # blank name => not a valid link target (PR6 fail-closed)
        out.append(Plot(plot_id=plot_id, contributor_name=contributor))
    out.sort(key=lambda p: p.plot_id)
    return out


# -- Rendering / CLI ----------------------------------------------------------


def render_plan(pairings: Iterable[Pairing], unallocated: Iterable[SoldQr]) -> str:
    lines = []
    pairings = list(pairings)
    unallocated = list(unallocated)
    n_tree = sum(1 for p in pairings if p.kind == "tree")
    n_plot = sum(1 for p in pairings if p.kind == "plot")
    lines.append(
        f"Proposed pairings: {len(pairings)} "
        f"({n_tree} tree, {n_plot} plot) | unallocated: {len(unallocated)}"
    )
    for p in pairings:
        lines.append(
            f"  {p.qr_code}  ->  [{p.kind}] {p.target_id}"
            f"  (farmer: {p.contributor_name or 'UNKNOWN'})  — {p.reason}"
        )
    if unallocated:
        lines.append("Unallocated (no target left):")
        for q in unallocated:
            lines.append(f"  {q.qr_code}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Batch-allocate sold-but-unlinked QR codes to SunMint tree/plot links "
            "(plan PR7). Dry-run by default; --execute --yes submits the link "
            "events (ledger-money gate — governor present)."
        )
    )
    p.add_argument(
        "--execute",
        action="store_true",
        help="Submit the link events (default: dry-run).",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="Required with --execute (ledger-money gate acknowledgement).",
    )
    p.add_argument(
        "--updated-by",
        default="Sophia Truesight",
        help="The governor identity on each event.",
    )
    p.add_argument(
        "--max-links",
        type=int,
        default=None,
        help="Cap total pairings (e.g. the settled-pool balance).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only consider the first N sold-unlinked QRs.",
    )
    p.add_argument(
        "--json-out", default=None, help="Write the pairing plan as JSON to this path."
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    gc = _gspread_client()
    qrs = load_sold_unlinked_qrs(gc)
    trees = load_tree_units(gc)
    plots = load_plots(gc)
    if args.limit is not None:
        qrs = sorted(qrs, key=lambda q: (q.sold_date or "", q.qr_code))[: args.limit]

    pairings, unallocated = compute_allocations(
        qrs, trees, plots, available_units=args.max_links
    )

    print(render_plan(pairings, unallocated))
    print(
        f"\nInputs: {len(qrs)} sold-unlinked QRs, {len(trees)} eligible tree units, "
        f"{len(plots)} eligible plots."
    )

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "pairings": [p.__dict__ for p in pairings],
                    "unallocated": [q.__dict__ for q in unallocated],
                },
                fh,
                indent=2,
            )
        print(f"Plan written to {args.json_out}")

    if not args.execute:
        print("\nDRY-RUN — no link event fired, no ledger write. Nothing changed.")
        return 0

    if not args.yes:
        print(
            "\nREFUSING TO EXECUTE: --execute books ledger rows (the plan's "
            "ledger-money gate). Re-run with --yes once a governor has reviewed "
            "the plan above and said go."
        )
        return 2

    from ..edgar_client import EdgarClient

    client = EdgarClient.from_env()
    sent = 0
    for pairing in pairings:
        attrs = build_link_attributes(pairing, args.updated_by)
        resp = client.submit(EVENT_TAG, attrs)
        ok = getattr(resp, "ok", False)
        print(
            f"  submitted {pairing.qr_code} -> {pairing.kind}:{pairing.target_id} ({resp.status_code})"
        )
        sent += 1 if ok else 0
    print(f"\nExecuted: {sent}/{len(pairings)} link event(s) submitted.")
    return 0 if sent == len(pairings) else 1


if __name__ == "__main__":
    sys.exit(main())
