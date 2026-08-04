"""Tests that the CLI uses the configured TOOLKINETIK_API_URL (#14).

SPEC: docs/SPEC-25-improvements.md #14
Tier 2 — cli.py must not hardcode localhost:8000; it must read
settings.TOOLKINETIK_API_URL.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from toolkinetik.cli import app

runner = CliRunner()


@pytest.fixture
def remote_url(monkeypatch: pytest.MonkeyPatch):
    """Point the CLI at a non-default API URL via env var.

    Settings is lru_cached; clear the cache so the new env is picked up.
    """
    monkeypatch.setenv("TOOLKINETIK_API_URL", "http://remote:9000")
    from toolkinetik import config
    config.get_settings.cache_clear()
    # Also re-import cli module-level settings so API_BASE refreshes.
    import importlib

    import toolkinetik.cli as cli_mod
    importlib.reload(cli_mod)
    yield "http://remote:9000"
    config.get_settings.cache_clear()
    importlib.reload(cli_mod)


class TestCliApiUrl:
    def test_health_uses_configured_url(self, remote_url: str):
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {"status": "healthy"}
        with patch("toolkinetik.cli.httpx.get", return_value=mock_response) as mock_get:
            runner.invoke(app, ["health"])
        called_url = mock_get.call_args[0][0]
        assert called_url == f"{remote_url}/api/health"

    def test_skills_list_uses_configured_url(self, remote_url: str):
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {"tools": []}
        with patch("toolkinetik.cli.httpx.get", return_value=mock_response) as mock_get:
            runner.invoke(app, ["skills", "list"])
        called_url = mock_get.call_args[0][0]
        assert called_url == f"{remote_url}/api/skills"

    def test_skills_reload_uses_configured_url(self, remote_url: str):
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {"status": "success", "loaded_tools": []}
        with patch("toolkinetik.cli.httpx.post", return_value=mock_response) as mock_post:
            runner.invoke(app, ["skills", "reload"])
        called_url = mock_post.call_args[0][0]
        assert called_url == f"{remote_url}/api/reload-skills"

    def test_default_url_is_localhost(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TOOLKINETIK_API_URL", raising=False)
        from toolkinetik import config
        config.get_settings.cache_clear()
        import importlib

        import toolkinetik.cli as cli_mod
        importlib.reload(cli_mod)
        try:
            assert cli_mod.API_BASE == "http://localhost:8000"
        finally:
            config.get_settings.cache_clear()
            importlib.reload(cli_mod)