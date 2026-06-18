#!/usr/bin/env python3
"""Submit [CONTRIBUTOR ADD EVENT] to Edgar.

Browser equivalent: dapp.truesight.me/governor_contributor_admin.html

Run:
    python -m truesight_dao_client.modules.add_contributor --help
    # or: truesight-dao-add-contributor --help
"""
import sys

from ..edgar_client import build_event_cli

main = build_event_cli(
    event_name='CONTRIBUTOR ADD EVENT',
    canonical_labels=[
        'Contributor Name',
        'Contributor Email',
        'Initial Digital Signature',
        'Submitted At',
        'Submission Source',
    ],
    dapp_page='governor_contributor_admin.html',
    required_labels=['Contributor Name', 'Contributor Email'],
)

if __name__ == "__main__":
    sys.exit(main())
