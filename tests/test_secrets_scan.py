"""Tests for secrets scan (P0.6).

Verifies that the repository history is free of high-severity secrets.
This test runs gitleaks if available; otherwise skips with a clear reason.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _gitleaks_available() -> str | None:
    """Return gitleaks binary path if available, else None."""
    return shutil.which("gitleaks") or shutil.which("/tmp/opencode/gitleaks")


def test_no_secrets_in_git_history():
    """gitleaks scan over the full git history finds no leaks.

    SPEC: docs/SPEC-production-readiness.md P0.6
    Tier 3 — Security: no API keys, tokens, or passwords in git history.
    """
    gitleaks = _gitleaks_available()
    if gitleaks is None:
        pytest.skip("gitleaks not installed — run `gitleaks git -v` manually")

    proc = subprocess.run(
        [gitleaks, "git", "-v", "--redact"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    if proc.returncode == 0:
        return  # no leaks found

    # Non-zero exit means leaks were found — fail with details.
    pytest.fail(
        f"gitleaks found secrets in git history (exit {proc.returncode}):\n"
        f"{proc.stdout}\n{proc.stderr}"
    )


def test_no_secrets_in_working_tree():
    """gitleaks scan over the working tree (staged + unstaged) finds no leaks."""
    gitleaks = _gitleaks_available()
    if gitleaks is None:
        pytest.skip("gitleaks not installed")

    proc = subprocess.run(
        [gitleaks, "dir", "-v", "--redact", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if proc.returncode == 0:
        return

    pytest.fail(
        f"gitleaks found secrets in working tree (exit {proc.returncode}):\n"
        f"{proc.stdout}\n{proc.stderr}"
    )