"""Tests for API-key production policy (P0.5).

SPEC: docs/SPEC-production-readiness.md P0.5
Tier 3 — Security: in production, AGNO_API_KEY must be set explicitly;
auto-generation is only allowed in dev mode (TOOLKINETIK_DEV=1).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from toolkinetik.config import _load_or_generate_api_key


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Clear all key-related env vars and point data dir at tmp."""
    monkeypatch.delenv("AGNO_API_KEY", raising=False)
    monkeypatch.delenv("TOOLKINETIK_API_KEY", raising=False)
    monkeypatch.delenv("TOOLKINETIK_DEV", raising=False)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


def _file_mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


class TestProductionKeyPolicy:
    def test_production_without_env_key_raises(self, isolated_env: Path):
        """Production mode (no TOOLKINETIK_DEV) without AGNO_API_KEY → RuntimeError."""
        key_file = isolated_env / ".api_key"
        with patch("toolkinetik.config._api_key_file", return_value=key_file), pytest.raises(RuntimeError, match="AGNO_API_KEY"):
            _load_or_generate_api_key()

    def test_production_without_env_key_no_file_created(self, isolated_env: Path):
        """Production mode must not create a key file on failure."""
        key_file = isolated_env / ".api_key"
        with patch("toolkinetik.config._api_key_file", return_value=key_file), pytest.raises(RuntimeError):
            _load_or_generate_api_key()
        assert not key_file.exists()

    def test_production_with_env_key_works(self, isolated_env: Path, monkeypatch: pytest.MonkeyPatch):
        """Production mode with AGNO_API_KEY set → uses env key, no file."""
        monkeypatch.setenv("AGNO_API_KEY", "prod-secret")
        key_file = isolated_env / ".api_key"
        with patch("toolkinetik.config._api_key_file", return_value=key_file):
            key = _load_or_generate_api_key()
        assert key == "prod-secret"
        assert not key_file.exists()

    def test_production_with_toolkinetik_api_key_works(self, isolated_env: Path, monkeypatch: pytest.MonkeyPatch):
        """TOOLKINETIK_API_KEY also works in production."""
        monkeypatch.setenv("TOOLKINETIK_API_KEY", "tk-prod-secret")
        key_file = isolated_env / ".api_key"
        with patch("toolkinetik.config._api_key_file", return_value=key_file):
            key = _load_or_generate_api_key()
        assert key == "tk-prod-secret"

    def test_production_with_existing_key_file_works(self, isolated_env: Path):
        """Production mode with an existing persisted key file → reads it."""
        key_file = isolated_env / ".api_key"
        key_file.write_text("persisted-secret")
        os.chmod(key_file, 0o600)
        with patch("toolkinetik.config._api_key_file", return_value=key_file):
            key = _load_or_generate_api_key()
        assert key == "persisted-secret"


class TestDevModeKeyPolicy:
    def test_dev_mode_allows_auto_gen(self, isolated_env: Path, monkeypatch: pytest.MonkeyPatch):
        """Dev mode (TOOLKINETIK_DEV=1) without env key → auto-generates."""
        monkeypatch.setenv("TOOLKINETIK_DEV", "1")
        key_file = isolated_env / ".api_key"
        with patch("toolkinetik.config._api_key_file", return_value=key_file):
            key = _load_or_generate_api_key()
        assert key  # non-empty
        assert key_file.exists()
        assert _file_mode(key_file) == 0o600

    def test_dev_mode_env_key_takes_precedence(self, isolated_env: Path, monkeypatch: pytest.MonkeyPatch):
        """Dev mode with env key set → uses env key, no auto-gen."""
        monkeypatch.setenv("TOOLKINETIK_DEV", "1")
        monkeypatch.setenv("AGNO_API_KEY", "dev-env-secret")
        key_file = isolated_env / ".api_key"
        with patch("toolkinetik.config._api_key_file", return_value=key_file):
            key = _load_or_generate_api_key()
        assert key == "dev-env-secret"
        assert not key_file.exists()

    def test_dev_mode_existing_key_file_reused(self, isolated_env: Path, monkeypatch: pytest.MonkeyPatch):
        """Dev mode with existing key file → reads it, no new gen."""
        monkeypatch.setenv("TOOLKINETIK_DEV", "1")
        key_file = isolated_env / ".api_key"
        key_file.write_text("existing-dev-key")
        os.chmod(key_file, 0o600)
        with patch("toolkinetik.config._api_key_file", return_value=key_file):
            key = _load_or_generate_api_key()
        assert key == "existing-dev-key"