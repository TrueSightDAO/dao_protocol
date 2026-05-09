#!/usr/bin/env python3
"""Submit [CONTRIBUTION EVENT] to Edgar.

Browser equivalent: dapp.truesight.me/report_contribution.html

Run:
    python -m truesight_dao_client.modules.report_contribution --help
    # or: truesight-dao-report-contribution --help
"""
import sys

from ..edgar_client import build_event_cli

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


main = build_event_cli(
    event_name='CONTRIBUTION EVENT',
    canonical_labels=['Type', 'Amount', 'Description', 'Contributor(s)', 'TDG Issued', 'Attached Filename', 'Destination Contribution File Location'],
    dapp_page='report_contribution.html',
    validators={'Type': _validate_contribution_type},
    normalizers={'Contributor(s)': _normalize_contributors},
)

if __name__ == "__main__":
    sys.exit(main())
