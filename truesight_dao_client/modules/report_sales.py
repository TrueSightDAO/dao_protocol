#!/usr/bin/env python3
"""Submit [SALES EVENT] to Edgar.

Browser equivalent: dapp.truesight.me/report_sales.html

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.report_sales --help

Note on name fields:
  "Sold by" and "Cash proceeds collected by" in the DApp are populated from
  the Agroverse QR codes sheet (Column U = Manager Name). The CLI does not
  yet validate against that live list; the operator is responsible for using
  the canonical manager name.
"""
import sys
import warnings

from ..edgar_client import build_event_cli
from ..validators import strip_email_addresses

_inner_main = build_event_cli(
    event_name='SALES EVENT',
    canonical_labels=['Item', 'Sales price', 'Sold by', 'Cash proceeds collected by', 'Owner email', 'Stripe Session ID', 'Shipping Provider', 'Tracking number', 'Attached Filename', 'Submission Source'],
    dapp_page='report_sales.html',
    normalizers={
        'Sold by': strip_email_addresses,
        'Cash proceeds collected by': strip_email_addresses,
    },
    defaults={'Submission Source': 'CLI'},
    required_labels=['Owner email'],
)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    qr_code_value = None
    item_present = False
    filtered = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--qr-code':
            if i + 1 >= len(argv) or argv[i + 1].startswith('--'):
                print("error: --qr-code requires a value", file=sys.stderr)
                return 2
            qr_code_value = argv[i + 1]
            i += 2
        elif a.startswith('--item='):
            item_present = True
            filtered.append(a)
            i += 1
        elif a == '--item':
            item_present = True
            filtered.append(a)
            i += 1
            if i < len(argv) and not argv[i].startswith('--'):
                filtered.append(argv[i])
                i += 1
        else:
            filtered.append(a)
            i += 1

    if qr_code_value is not None:
        # --qr-code takes precedence over --item
        cleaned = []
        j = 0
        while j < len(filtered):
            a = filtered[j]
            if a.startswith('--item='):
                j += 1
            elif a == '--item':
                j += 1
                if j < len(filtered) and not filtered[j].startswith('--'):
                    j += 1
            else:
                cleaned.append(a)
                j += 1
        cleaned.extend(['--item', qr_code_value])
        filtered = cleaned
    elif item_present:
        warnings.warn(
            "The --item flag is deprecated; use --qr-code to specify the QR code identifier.",
            DeprecationWarning,
            stacklevel=2,
        )

    return _inner_main(filtered)


if __name__ == "__main__":
    sys.exit(main())
