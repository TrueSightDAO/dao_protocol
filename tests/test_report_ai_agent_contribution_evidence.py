"""Tests for report_ai_agent_contribution's PR/commit evidence validation.

Added 2026-07-22: an interactive session merged several branches directly
(governor said "merge and deploy", no PR review cycle) and then had no PR URL
to cite when filing the AI-agent contribution — the CLI required one and
rejected everything else, including a plain commit URL. Extended the
validator to accept a TrueSightDAO commit URL as a fallback, since it's still
real, verifiable GitHub evidence. See
agentic_ai_context/dao/DAO_CLIENT_AI_AGENT_CONTRIBUTIONS.md.
"""

from __future__ import annotations

import pytest

from truesight_dao_client.modules.report_ai_agent_contribution import (
    _is_valid_evidence_url,
    main,
)


def test_pull_request_url_is_valid():
    assert _is_valid_evidence_url(
        "https://github.com/TrueSightDAO/dao_client/pull/42"
    )


def test_pull_request_url_with_trailing_slash_is_valid():
    assert _is_valid_evidence_url(
        "https://github.com/TrueSightDAO/dao_client/pull/42/"
    )


def test_commit_url_full_sha_is_valid():
    assert _is_valid_evidence_url(
        "https://github.com/TrueSightDAO/truesight_autopilot/commit/"
        "347a8b0123456789abcdef0123456789abcdef01"
    )


def test_commit_url_short_sha_is_valid():
    assert _is_valid_evidence_url(
        "https://github.com/TrueSightDAO/truesight_autopilot/commit/347a8b0"
    )


def test_commit_url_too_short_sha_is_invalid():
    # Fewer than 7 hex chars — not a real GitHub short-SHA reference.
    assert not _is_valid_evidence_url(
        "https://github.com/TrueSightDAO/truesight_autopilot/commit/347a8"
    )


def test_commits_listing_url_is_invalid():
    # The branch-history LISTING page, not a specific commit — must not
    # slip through as "evidence" of a specific change.
    assert not _is_valid_evidence_url(
        "https://github.com/TrueSightDAO/truesight_autopilot/commits/main"
    )


def test_non_truesightdao_org_is_invalid():
    assert not _is_valid_evidence_url(
        "https://github.com/someoneelse/dao_client/commit/347a8b0"
    )


def test_non_github_host_is_invalid():
    assert not _is_valid_evidence_url(
        "https://gitlab.com/TrueSightDAO/dao_client/commit/347a8b0"
    )


def test_main_rejects_when_no_pr_or_commit_given(capsys):
    with pytest.raises(SystemExit):
        main(
            [
                "--title", "t",
                "--body", "b",
                "--type", "Time (Minutes)",
                "--minutes", "10",
            ]
        )
    assert "At least one --pr URL is required" in capsys.readouterr().err


def test_main_rejects_invalid_evidence_url(capsys):
    with pytest.raises(SystemExit):
        main(
            [
                "--title", "t",
                "--body", "b",
                "--type", "Time (Minutes)",
                "--minutes", "10",
                "--pr", "https://github.com/TrueSightDAO/dao_client/issues/1",
            ]
        )
    assert "Invalid --pr" in capsys.readouterr().err
