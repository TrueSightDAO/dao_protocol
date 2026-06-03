#!/usr/bin/env python3
"""Submit `[PROGRAM REGISTRATION REQUEST]` to Edgar.

Step 1 of the two-step self-serve program-onboarding flow (a governor approves in
step 2 before anything is provisioned). Anyone with a registered digital signature
(a partner admin or a sponsoring contributor) submits the program definition; it
lands as a PENDING row on the `Program Registrations` tab — NO provisioning yet.

Browser equivalent: dapp.truesight.me/report_program_registration.html
Blueprint + parameter set + approval/provisioning design:
  agentic_ai_context/PROGRAM_PARTNER_ONBOARDING.md ("Two-step [PROGRAM REGISTRATION]").

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.report_program_registration --help

Typical use:
    python -m truesight_dao_client.modules.report_program_registration \\
        --program-slug butterfly-effect \\
        --display-name "Butterfly Effect" \\
        --description "ERA Professionals experiential-learning cohort." \\
        --website "https://era-professionals.com" \\
        --partner-organization "ERA Professionals" \\
        --capabilities "credentialing,tree_planting" \\
        --roster-sheet-url "https://docs.google.com/spreadsheets/d/.../edit" \\
        --admin-subdomain "butterfly-effect-club.truesight.me"
"""
import sys

from ..edgar_client import build_event_cli

# Canonical payload labels = the consolidated program-definition parameter set.
# Capabilities (csv): credentialing | activity_reporting | tree_planting | donation.
# Currency/Ledger Codename/Price/Origin Identity are only needed for tree_planting/donation.
main = build_event_cli(
    event_name='PROGRAM REGISTRATION REQUEST',
    canonical_labels=[
        'Program Slug',
        'Display Name',
        'Description',
        'Logo URL',
        'Website',
        'Partner Organization',
        'Capabilities',
        'Roster Sheet URL',
        'Admin Subdomain',
        'Currency',
        'Ledger Codename',
        'Price',
        'Origin Identity',
        'Submission Source',
    ],
    dapp_page='report_program_registration.html',
)

if __name__ == "__main__":
    sys.exit(main())
