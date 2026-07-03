#!/usr/bin/env python3
"""Submit [CONTRIBUTION EVENT] to Edgar.

Browser equivalent: dapp.truesight.me/report_contribution.html

TDG Issued is computed from Type + Amount; --tdg-issued is accepted for
backward-compat but ignored (a warning is printed if it disagrees).

Run:
    python -m truesight_dao_client.modules.report_contribution --help
    # or: truesight-dao-report-contribution --help
"""
import sys

from ..edgar_client import build_event_cli
from ..rubric import tdg_for, format_tdg
from ..validators import dao_contributor_name, strip_email_addresses

# Canonical rubric types from the TrueSight DAO Intiatives Scoring Rubric.
# See Main Ledger & Contributors spreadsheet, tab "Intiatives Scoring Rubric".
VALID_CONTRIBUTION_TYPES = {
    "Time (Minutes)",
    "USD",
    "USDT sent",
    "USDT received",
}

# Grok scoring splits comma-separated contributors into separate rows.
# Slash or ampersand formats ("Kimi / Gary", "Kimi & Gary") stay as one
# combined string, which breaks ledger allocation. Always use commas.
CONTRIBUTOR_SEPARATOR = ", "


def _validate_contribution_type(value: str) -> None:
    """Raise ValueError if the contribution Type is not a valid rubric entry."""
    if value not in VALID_CONTRIBUTION_TYPES:
        raise ValueError(
            f"Invalid contribution Type: {value!r}. "
            f"Must be one of: {', '.join(sorted(VALID_CONTRIBUTION_TYPES))}. "
            f"See Intiatives Scoring Rubric in Main Ledger."
        )


def _normalize_contributors(value: str) -> str:
    """Normalize slash/ampersand separators to commas so Grok scoring splits correctly."""
    v = (value or "").strip()
    # Replace common multi-contributor separators with comma + space
    v = v.replace(" / ", CONTRIBUTOR_SEPARATOR)
    v = v.replace("/", CONTRIBUTOR_SEPARATOR)
    v = v.replace(" & ", CONTRIBUTOR_SEPARATOR)
    v = v.replace("; ", CONTRIBUTOR_SEPARATOR)
    # Deduplicate spaces around commas
    parts = [p.strip() for p in v.split(",") if p.strip()]
    return CONTRIBUTOR_SEPARATOR.join(parts)


def _authoritative_tdg(attrs):
    """Recompute 'TDG Issued' from Type + Amount. Ignore (and warn about) any
    caller-supplied --tdg-issued that disagrees. TDG is computed, never supplied."""
    d = dict(attrs)
    ctype = d.get("Type")
    amount = d.get("Amount")
    if ctype is None or amount is None:
        return attrs
    computed = format_tdg(tdg_for(ctype, amount))
    supplied = d.get("TDG Issued")
    if supplied is not None and str(supplied).strip() != computed:
        print(
            f"[report-contribution] --tdg-issued {supplied!r} IGNORED; using rubric value "
            f"{computed} (Type={ctype!r}, Amount={amount!r}). TDG is computed, not client-supplied.",
            file=sys.stderr,
        )
    out, replaced = [], False
    for lbl, val in attrs:
        if lbl == "TDG Issued":
            out.append((lbl, computed))
            replaced = True
        else:
            out.append((lbl, val))
    if not replaced:
        idx = next((i for i, (l, _) in enumerate(out) if l == "Contributor(s)"), len(out) - 1)
        out.insert(idx + 1, ("TDG Issued", computed))
    return out


main = build_event_cli(
    event_name='CONTRIBUTION EVENT',
    canonical_labels=['Type', 'Amount', 'Description', 'Contributor(s)', 'TDG Issued', 'Attached Filename', 'Destination Contribution File Location'],
    dapp_page='report_contribution.html',
    required_labels=['Type', 'Amount', 'Contributor(s)'],
    validators={
        'Type': _validate_contribution_type,
        'Contributor(s)': dao_contributor_name,
    },
    normalizers={
        'Contributor(s)': lambda v: strip_email_addresses(_normalize_contributors(v)),
    },
    derive=_authoritative_tdg,
)

if __name__ == "__main__":
    sys.exit(main())
