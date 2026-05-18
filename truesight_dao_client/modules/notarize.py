#!/usr/bin/env python3
"""Submit [NOTARIZATION EVENT] to Edgar.

Browser equivalent: dapp.truesight.me/notarize.html

Run from the dao_client repo root:
    python -m truesight_dao_client.modules.notarize --help
"""
import re
import sys

from ..edgar_client import build_event_cli

# Canonical notarizations repository — Edgar uploads attachments here.
_NOTARIZATIONS_REPO = "TrueSightDAO/notarizations"
_NOTARIZATIONS_BASE_URL = f"https://github.com/{_NOTARIZATIONS_REPO}/blob/main/"


def _normalize_destination_url(value: str) -> str:
    """
    Ensure the destination URL always lands in the canonical notarizations repo.

    - Bare filename -> auto-prefix with canonical base URL.
    - Wrong repo (e.g. treasury-cache) -> auto-correct to canonical repo.
    - Already correct -> passthrough.
    """
    v = (value or "").strip()
    if not v:
        return v

    # If it's just a filename (no protocol, no slashes that look like a path),
    # prefix with the canonical base URL.
    if not v.startswith("http") and "/" not in v:
        return _NOTARIZATIONS_BASE_URL + v

    # If it points to the wrong repo, rewrite it.
    # This catches treasury-cache/notarizations/... and similar mistakes.
    wrong_repo_pattern = re.compile(
        r"https://github\.com/[^/]+/treasury-cache/blob/[^/]+/notarizations/(.+)"
    )
    m = wrong_repo_pattern.match(v)
    if m:
        return _NOTARIZATIONS_BASE_URL + m.group(1)

    # If it already points to the right repo, leave it alone.
    if v.startswith(_NOTARIZATIONS_BASE_URL):
        return v

    # Any other URL: try to extract a trailing path/filename and rewrite.
    # e.g. https://github.com/SomeOrg/some-repo/blob/main/path/to/file.pdf
    generic_pattern = re.compile(
        r"https://github\.com/[^/]+/[^/]+/blob/[^/]+/(.+)"
    )
    m = generic_pattern.match(v)
    if m:
        return _NOTARIZATIONS_BASE_URL + m.group(1)

    return v


def _validate_destination_url(value: str) -> None:
    """
    Raise ValueError if the destination URL cannot be normalized into the canonical repo.
    Accepts bare filenames, correct URLs, or wrong-repo URLs (the normalizer fixes those).
    """
    v = (value or "").strip()
    if not v:
        return  # let normalizer/Edgar handle empty if needed

    # Bare filename is fine — normalizer will prefix it.
    if not v.startswith("http") and "/" not in v:
        return

    # Any github.com blob URL is fine — normalizer will extract the path.
    if re.match(r"https://github\.com/[^/]+/[^/]+/blob/", v):
        return

    raise ValueError(
        f"Destination Notarized File Location must be a GitHub blob URL or bare filename. "
        f"Got: {v!r}."
    )


main = build_event_cli(
    event_name='NOTARIZATION EVENT',
    canonical_labels=['Submitter', 'Latitude', 'Longitude', 'Document Type', 'Description', 'Attached Filename', 'Destination Notarized File Location', 'Submission Source'],
    dapp_page='notarize.html',
    validators={'Destination Notarized File Location': _validate_destination_url},
    normalizers={'Destination Notarized File Location': _normalize_destination_url},
)

if __name__ == "__main__":
    sys.exit(main())
