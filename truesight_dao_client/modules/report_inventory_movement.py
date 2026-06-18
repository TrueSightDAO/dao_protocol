#!/usr/bin/env python3
"""Submit [INVENTORY MOVEMENT] to Edgar.

Browser equivalent: dapp.truesight.me/report_inventory_movement.html

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.report_inventory_movement --help
"""
import sys

from ..edgar_client import build_event_cli
from ..validators import (
    inventory_item,
    latitude,
    longitude,
    manager_name,
    positive_integer,
)

main = build_event_cli(
    event_name='INVENTORY MOVEMENT',
    canonical_labels=['Manager Name', 'Recipient Name', 'Inventory Item', 'QR Code', 'Quantity', 'Latitude', 'Longitude', 'Attached Filename', 'Destination Inventory File Location', 'Submission Source'],
    dapp_page='report_inventory_movement.html',
    validators={
        'Manager Name': manager_name,
        'Inventory Item': inventory_item,
        'Quantity': positive_integer,
        'Latitude': latitude,
        'Longitude': longitude,
    },
)

if __name__ == "__main__":
    sys.exit(main())
