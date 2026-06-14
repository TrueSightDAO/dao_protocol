#!/usr/bin/env python3
"""Submit [PARTNER ADD EVENT] to Edgar.

Onboards a new retail partner to the DAO Partners sheet.

Run:
    python -m truesight_dao_client.modules.add_partner --help
    # or: truesight-dao-add-partner --help
"""
import sys

from ..edgar_client import build_event_cli

VALID_PARTNER_TYPES = {"Wholesale", "Consignment"}


def _validate_partner_type(value: str) -> None:
    """Raise ValueError if the partner Type is not valid."""
    if value not in VALID_PARTNER_TYPES:
        raise ValueError(
            f"Invalid partner Type: {value!r}. "
            f"Must be one of: {', '.join(sorted(VALID_PARTNER_TYPES))}."
        )


main = build_event_cli(
    event_name='PARTNER ADD EVENT',
    canonical_labels=[
        'Partner Name',
        'Email',
        'Address',
        'Type',
        'Website',
        'About',
        'Governor Name',
    ],
    dapp_page=None,
    validators={'Type': _validate_partner_type},
)

if __name__ == "__main__":
    sys.exit(main())
