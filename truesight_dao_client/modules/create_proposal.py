#!/usr/bin/env python3
"""Submit [PROPOSAL CREATION] to Edgar.

Browser equivalent: dapp.truesight.me/create_proposal.html

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.create_proposal --help

Flags:
  --type              Proposal type: standard, vendor, governance, budget (required)
  --title             Short proposal title, max 120 chars (required)
  --content           Full proposal body (required unless --body-file given)
  --body-file         Path to file containing proposal body (alternative to --content)
  --performance-metrics  URL or reference to performance data (optional, for vendor proposals)
"""
import os
import sys

from ..edgar_client import build_event_cli

_inner_main = build_event_cli(
    event_name='PROPOSAL CREATION',
    canonical_labels=['Type', 'Title', 'Content', 'Performance Metrics'],
    dapp_page='create_proposal.html',
    required_labels=['Type', 'Title'],
)


VALID_TYPES = {'standard', 'vendor', 'governance', 'budget'}
VALID_VOTE_CHOICES = {'approve', 'reject', 'abstain'}


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    body_file_path = None
    filtered = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--body-file':
            if i + 1 >= len(argv) or argv[i + 1].startswith('--'):
                print("error: --body-file requires a value", file=sys.stderr)
                return 2
            body_file_path = argv[i + 1]
            i += 2
        elif a.startswith('--body-file='):
            body_file_path = a.split('=', 1)[1]
            i += 1
        else:
            filtered.append(a)
            i += 1

    # Read body file if provided, inject as --content
    if body_file_path is not None:
        if not os.path.isfile(body_file_path):
            print(f"error: body file not found: {body_file_path}", file=sys.stderr)
            return 2
        try:
            with open(body_file_path, 'r') as f:
                body_content = f.read()
        except IOError as e:
            print(f"error: could not read body file: {e}", file=sys.stderr)
            return 2
        filtered.extend(['--content', body_content])

    # Validate --type before passing to inner main
    type_value = None
    for j, a in enumerate(filtered):
        if a == '--type' and j + 1 < len(filtered) and not filtered[j + 1].startswith('--'):
            type_value = filtered[j + 1]
            break
        if a.startswith('--type='):
            type_value = a.split('=', 1)[1]
            break

    if type_value is not None and type_value.lower() not in VALID_TYPES:
        print(
            f"error: invalid --type '{type_value}'. Choose from: {', '.join(sorted(VALID_TYPES))}",
            file=sys.stderr,
        )
        return 2

    return _inner_main(filtered)


if __name__ == "__main__":
    sys.exit(main())
