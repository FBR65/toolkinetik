"""Tests for the Typer CLI (cli.py).

All httpx calls are mocked so no real server connection is needed.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
from typer.testing import CliRunner

from agno_agent_os.cli import app

runner = CliRunner()


def test_health_command() -> None:
    """`health` command hits /api/health and prints 'healthy'."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "healthy"}

    with patch("agno_agent_os.cli.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["health"])

    assert result.exit_code == 0
    assert "healthy" in result.output


def test_skills_list_command() -> None:
    """`skills list` command fetches skills and prints their names."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"tools": ["get_current_weather", "calculate_fibonacci"]}

    with patch("agno_agent_os.cli.httpx.get", return_value=mock_response):
        result = runner.invoke(app, ["skills", "list"])

    assert result.exit_code == 0
    assert "get_current_weather" in result.output or "calculate_fibonacci" in result.output


def test_skills_reload_command() -> None:
    """`skills reload` triggers reload and mentions 'reload' in output."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "success", "loaded_tools": ["echo"]}

    with patch("agno_agent_os.cli.httpx.post", return_value=mock_response):
        result = runner.invoke(app, ["skills", "reload"])

    assert result.exit_code == 0
    assert "reload" in result.output.lower()


def test_skills_create_command() -> None:
    """`skills create` accepts name and description arguments."""
    result = runner.invoke(app, ["skills", "create", "my_skill", "A test skill"])
    assert result.exit_code == 0
    assert "my_skill" in result.output


def test_sandbox_status_command() -> None:
    """`sandbox status` prints Docker status."""
    result = runner.invoke(app, ["sandbox", "status"])
    assert result.exit_code == 0
    assert "Docker" in result.output