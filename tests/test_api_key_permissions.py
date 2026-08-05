"""Tests for API-key file permissions (#2).

SPEC: docs/SPEC-25-improvements.md #2
Tier 3 — Security: persisted API key file must have mode 0o600.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from toolkinetik.config import _load_or_generate_api_key


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the API-key file at a tmp data dir and clear env keys.

    Sets TOOLKINETIK_DEV=1 so auto-generation is allowed (these tests
    verify the auto-gen file-permission behaviour, which is dev-mode only).
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AGNO_API_KEY", raising=False)
    monkeypatch.delenv("TOOLKINETIK_API_KEY", raising=False)
    monkeypatch.setenv("TOOLKINETIK_DEV", "1")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


def _key_path_in(data_dir: Path) -> Path:
    """Compute the key path as config would, given a data dir."""
    with patch("toolkinetik.config._api_key_file", return_value=data_dir / ".api_key"):
        return data_dir / ".api_key"


def _file_mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


class TestApiKeyFilePermissions:
    def test_new_key_file_has_mode_600(self, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch):
        key_file = isolated_data_dir / ".api_key"
        with patch("toolkinetik.config._api_key_file", return_value=key_file):
            key = _load_or_generate_api_key()
        assert key_file.exists()
        assert _file_mode(key_file) == 0o600
        assert key  # non-empty

    def test_existing_key_with_open_perms_is_corrected(self, isolated_data_dir: Path):
        key_file = isolated_data_dir / ".api_key"
        key_file.write_text("preexisting-secret")
        os.chmod(key_file, 0o644)
        with patch("toolkinetik.config._api_key_file", return_value=key_file):
            _load_or_generate_api_key()
        assert _file_mode(key_file) == 0o600
        assert key_file.read_text() == "preexisting-secret"

    def test_env_key_short_circuits_no_file_written(self, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AGNO_API_KEY", "env-secret")
        key_file = isolated_data_dir / ".api_key"
        with patch("toolkinetik.config._api_key_file", return_value=key_file):
            key = _load_or_generate_api_key()
        assert key == "env-secret"
        assert not key_file.exists()

    def test_toolkinetik_env_key_also_wins(self, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TOOLKINETIK_API_KEY", "tk-secret")
        key_file = isolated_data_dir / ".api_key"
        with patch("toolkinetik.config._api_key_file", return_value=key_file):
            key = _load_or_generate_api_key()
        assert key == "tk-secret"
        assert not key_file.exists()

    def test_existing_key_with_600_unchanged_mode(self, isolated_data_dir: Path):
        key_file = isolated_data_dir / ".api_key"
        key_file.write_text("already-secure")
        os.chmod(key_file, 0o600)
        with patch("toolkinetik.config._api_key_file", return_value=key_file):
            key = _load_or_generate_api_key()
        assert key == "already-secure"
        assert _file_mode(key_file) == 0o600