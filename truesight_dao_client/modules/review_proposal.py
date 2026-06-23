#!/usr/bin/env python3
"""Submit [PROPOSAL VOTE] to Edgar.

Browser equivalent: dapp.truesight.me/review_proposal.html

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.review_proposal --help

Flags:
  --proposal-id   PR number or proposal identifier (required)
  --vote          approve, reject, or abstain (required)
  --comment       Optional rationale for the vote
"""
import sys

from ..edgar_client import build_event_cli

_inner_main = build_event_cli(
    event_name='PROPOSAL VOTE',
    canonical_labels=['Proposal ID', 'Vote', 'Comment'],
    dapp_page='review_proposal.html',
    required_labels=['Proposal ID', 'Vote'],
)

VALID_VOTES = {'approve', 'reject', 'abstain'}


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Validate --vote before passing to inner main
    vote_value = None
    for j, a in enumerate(argv):
        if a == '--vote' and j + 1 < len(argv) and not argv[j + 1].startswith('--'):
            vote_value = argv[j + 1]
            break
        if a.startswith('--vote='):
            vote_value = a.split('=', 1)[1]
            break

    if vote_value is not None and vote_value.lower() not in VALID_VOTES:
        print(
            f"error: invalid --vote '{vote_value}'. Choose from: {', '.join(sorted(VALID_VOTES))}",
            file=sys.stderr,
        )
        return 2

    return _inner_main(argv)


if __name__ == "__main__":
    sys.exit(main())
