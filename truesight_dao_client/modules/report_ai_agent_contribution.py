#!/usr/bin/env python3
"""Submit [CONTRIBUTION EVENT] for AI agent work to Edgar (signed, DApp-equivalent).

Convention (full detail):
  https://github.com/TrueSightDAO/agentic_ai_context/blob/main/DAO_CLIENT_AI_AGENT_CONTRIBUTIONS.md

Requires:
  - ``./.env`` (cwd) with EMAIL, PUBLIC_KEY, PRIVATE_KEY (see README / ``truesight-dao-auth login``).
  - At least one --pr URL under https://github.com/TrueSightDAO/ (merged or open PR).

Run:
  python -m truesight_dao_client.modules.report_ai_agent_contribution --help
"""
from __future__ import annotations

import argparse
import os
import re
import sys

from ..edgar_client import EdgarClient
from .report_contribution import VALID_CONTRIBUTION_TYPES, _validate_contribution_type

DEFAULT_GEN = (
    "https://github.com/TrueSightDAO/agentic_ai_context/blob/main/DAO_CLIENT_AI_AGENT_CONTRIBUTIONS.md"
)
PR_PATTERN = re.compile(
    r"^https://github\.com/TrueSightDAO/[^/]+/pull/\d+/?(\?.*)?$",
    re.IGNORECASE,
)


def _contributors_from_email(email: str) -> str:
    """Derive default contributor name from EMAIL or CONTRIBUTOR_NAME env var.
    
    Prefers CONTRIBUTOR_NAME if set. Otherwise derives from EMAIL local-part.
    """
    name = (os.getenv("CONTRIBUTOR_NAME") or "").strip()
    if name:
        return name
    email = (email or "").strip()
    if "@" in email:
        return email.split("@", 1)[0].replace(".", " ").title() + f" <{email}>"
    return email or "AI Agent"


def _compute_amount_and_tdg(
    contribution_type: str, hours: float | None, minutes: float | None, usd: float | None
) -> tuple[str, str]:
    """Return (amount, tdg_issued) matching the DApp formula.

    Time:
      - Amount = total minutes (hours*60 + minutes)
      - TDG    = total hours * 100  (rounded to 2 decimals)
    USD:
      - Amount = USD value
      - TDG    = USD value
    """
    if contribution_type == "Time":
        h = hours or 0
        m = minutes or 0
        total_minutes = int(h * 60 + m)
        total_hours = h + m / 60.0
        tdg = round(total_hours * 100, 2)
        # Match DApp: whole minutes as string, TDG with 2 decimals
        return str(total_minutes), f"{tdg:.2f}"
    else:  # USD
        val = usd or 0
        return f"{val:.2f}", f"{val:.2f}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Submit [CONTRIBUTION EVENT] for AI agent work with mandatory TrueSightDAO PR links.",
    )
    p.add_argument("--title", required=True, help="Short title (prepended to Description).")
    p.add_argument(
        "--body",
        default=None,
        help="Multi-line description (include PR URLs here too). Use --body-file for long text.",
    )
    p.add_argument(
        "--body-file",
        default=None,
        metavar="PATH",
        help="Read description body from file (UTF-8).",
    )
    p.add_argument(
        "--pr",
        action="append",
        default=[],
        metavar="URL",
        help="Repeatable. Must match https://github.com/TrueSightDAO/<repo>/pull/<n>",
    )
    p.add_argument(
        "--type",
        required=True,
        choices=sorted(VALID_CONTRIBUTION_TYPES),
        help='Contribution type. Must match Intiatives Scoring Rubric. Valid: %(choices)s.',
    )
    p.add_argument(
        "--hours",
        type=float,
        default=0,
        help='Hours contributed (used when --type Time).',
    )
    p.add_argument(
        "--minutes",
        type=float,
        default=0,
        help='Minutes contributed (used when --type Time).',
    )
    p.add_argument(
        "--usd",
        type=float,
        default=0,
        help='USD amount (used when --type USD).',
    )
    p.add_argument(
        "--contributors",
        default=None,
        help='Maps to "Contributor(s)". Default: derived from EMAIL in .env.',
    )
    p.add_argument(
        "--generation-source",
        default=DEFAULT_GEN,
        help="This submission was generated using … (default: agentic_ai_context convention doc).",
    )
    p.add_argument("--dry-run", action="store_true", help="Print signed share text; do not POST.")
    args = p.parse_args(argv)

    if args.body and args.body_file:
        p.error("Use only one of --body or --body-file")

    body = args.body or ""
    if args.body_file:
        path = os.path.abspath(args.body_file)
        with open(path, "r", encoding="utf-8") as f:
            body = f.read()
    body = body.strip()
    if not body:
        p.error("Description body is required (--body or --body-file)")

    prs = list(args.pr or [])
    if not prs:
        p.error("At least one --pr URL is required (TrueSightDAO org pull request).")
    for url in prs:
        u = url.strip()
        if not PR_PATTERN.match(u):
            p.error(f"Invalid --pr (must be TrueSightDAO pull URL): {u!r}")

    # Normalize type to short form for internal logic
    _type_map = {
        "Time (Minutes)": "Time",
        "USD": "USD",
        "USDT sent": "USD",
        "USDT received": "USD",
    }
    internal_type = _type_map.get(args.type, "Time")

    # Validate type-specific inputs
    if internal_type == "Time":
        if args.hours <= 0 and args.minutes <= 0:
            p.error("--type Time requires --hours and/or --minutes > 0")
    elif internal_type == "USD":
        if args.usd <= 0:
            p.error("--type USD requires --usd > 0")

    amount, tdg_issued = _compute_amount_and_tdg(
        internal_type, args.hours, args.minutes, args.usd
    )

    # Use the canonical type label from the rubric, not the internal short form
    type_label = args.type if args.type in VALID_CONTRIBUTION_TYPES else "Time (Minutes)"

    pr_block = "Pull requests (GitHub evidence):\n" + "\n".join(f"- {u.strip()}" for u in prs)
    description = f"{args.title.strip()}\n\n{pr_block}\n\nDetails:\n{body}"

    client = EdgarClient.from_env()
    client.generation_source = args.generation_source.strip()

    contributors = args.contributors or _contributors_from_email(client.email)

    attrs: list[tuple[str, str]] = [
        ("Type", type_label),
        ("Amount", amount),
        ("Description", description),
        ("Contributor(s)", contributors),
        ("TDG Issued", tdg_issued),
        ("Attached Filename", "N/A"),
        ("Destination Contribution File Location", "N/A"),
    ]

    event_name = "CONTRIBUTION EVENT"
    if args.dry_run:
        payload, txn_id, share_text = client.sign(event_name, attrs)
        print(share_text)
        return 0

    resp = client.submit(event_name, attrs)
    print(f"HTTP {resp.status_code}")
    try:
        import json

        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)
    return 0 if resp.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
