#!/usr/bin/env python3
"""Submit [TREE PLANTING LINK EVENT] to Edgar.

Governor-only: links a Sunmint tree-planting submission (SunMint Tree Planting sheet, status NEW) to a
sold Agroverse QR code (status SOLD). Rejected server-side (GAS Governors tab check) if the signer isn't
a governor — signing with a non-governor identity will not succeed, it will just be logged and skipped.

Browser equivalent: dapp.truesight.me/link_tree_planting.html

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.link_tree_planting --help

Named flags (each maps to the exact label the GAS parser expects):

    --qr-code VALUE                       (label: QR Code)
    --sunmint-submission-message-id VALUE (label: SunMint Submission Message ID)
    --updated-by VALUE                    (label: Updated by)
    --submission-source VALUE             (label: Submission Source)

The --attr escape hatch also works. NOTE: the GAS handler (process_tree_planting_link.js) does not
currently parse "Submission Source" — it's included for consistency with events_catalog.json and the
general audit-trail convention other event types follow; an unrecognized line is harmless (ignored by
the GAS regex extraction), not an error.

See also:
    truesight_dao_client/server/data/events_catalog.json -> "TREE PLANTING LINK EVENT"
    agentic_ai_context/plans/SUNMINT_TREE_QR_LINKING_PLAN.md (PR6)
"""
import sys

from ..edgar_client import build_event_cli

main = build_event_cli(
    event_name='TREE PLANTING LINK EVENT',
    canonical_labels=[
        'QR Code',
        'SunMint Submission Message ID',
        'Updated by',
        'Submission Source',
    ],
    required_labels=['QR Code', 'SunMint Submission Message ID'],
    dapp_page='link_tree_planting.html',
)

if __name__ == "__main__":
    sys.exit(main())
