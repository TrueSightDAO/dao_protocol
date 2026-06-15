"""TrueSight DAO / Edgar Python client and CLIs (installable as ``truesight-dao-client``)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .edgar_client import EdgarClient, build_event_cli, generate_keypair

__all__ = ["EdgarClient", "build_event_cli", "generate_keypair", "__version__"]


def _get_git_commit_short() -> str:
    """Return the short Git commit hash, or 'dev' if not in a Git repo."""
    try:
        repo_root = Path(__file__).resolve().parent.parent
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(repo_root),
                stderr=subprocess.DEVNULL,
                text=True,
            )
            .strip()
        )
    except Exception:
        return "dev"


__version__ = _get_git_commit_short()
