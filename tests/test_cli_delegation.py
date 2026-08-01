"""Tests for CLIDelegator (Task 2.2)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agno_agent_os.coding_agent import (
    DEFAULT_CLI_CONFIGS,
    TASK_CLI_MAP,
    CLIDelegator,
)


# ---------------------------------------------------------------------------
# Init / config tests
# ---------------------------------------------------------------------------


def test_cli_delegator_init():
    delegator = CLIDelegator()
    assert "claude" in delegator.cli_configs
    assert "codex" in delegator.cli_configs
    assert "opencode" in delegator.cli_configs
    # Each config must have command, args, timeout
    for name, cfg in delegator.cli_configs.items():
        assert "command" in cfg
        assert "args" in cfg
        assert "timeout" in cfg


def test_cli_delegator_init_custom_configs():
    custom = {"mycli": {"command": "mycli", "args": ["--foo"], "timeout": 60}}
    delegator = CLIDelegator(cli_configs=custom)
    assert delegator.cli_configs == custom


def test_default_cli_configs_structure():
    assert DEFAULT_CLI_CONFIGS["claude"]["command"] == "claude"
    assert DEFAULT_CLI_CONFIGS["claude"]["args"] == ["--print"]
    assert DEFAULT_CLI_CONFIGS["codex"]["command"] == "codex"
    assert DEFAULT_CLI_CONFIGS["opencode"]["command"] == "opencode"


def test_task_cli_map_structure():
    assert TASK_CLI_MAP["feature"][0] == "claude"
    assert TASK_CLI_MAP["fix"][0] == "codex"
    assert TASK_CLI_MAP["refactor"][0] == "opencode"


# ---------------------------------------------------------------------------
# _select_cli tests
# ---------------------------------------------------------------------------


def test_select_cli_feature():
    delegator = CLIDelegator()
    assert delegator._select_cli("feature") == "claude"


def test_select_cli_fix():
    delegator = CLIDelegator()
    assert delegator._select_cli("fix") == "codex"


def test_select_cli_refactor():
    delegator = CLIDelegator()
    assert delegator._select_cli("refactor") == "opencode"


def test_select_cli_unknown_raises():
    delegator = CLIDelegator()
    with pytest.raises(ValueError):
        delegator._select_cli("bogus")


# ---------------------------------------------------------------------------
# _try_cli tests
# ---------------------------------------------------------------------------


def test_try_cli_success():
    delegator = CLIDelegator()
    mock_completed = MagicMock()
    mock_completed.stdout = "output from cli"
    mock_completed.stderr = ""
    mock_completed.returncode = 0
    with patch("agno_agent_os.coding_agent.subprocess.run", return_value=mock_completed):
        output, success = delegator._try_cli("claude", "do work")
    assert success is True
    assert output == "output from cli"


def test_try_cli_failure():
    delegator = CLIDelegator()
    mock_completed = MagicMock()
    mock_completed.stdout = ""
    mock_completed.stderr = "error happened"
    mock_completed.returncode = 1
    with patch("agno_agent_os.coding_agent.subprocess.run", return_value=mock_completed):
        output, success = delegator._try_cli("claude", "do work")
    assert success is False
    assert "error" in output


def test_try_cli_not_found():
    delegator = CLIDelegator()
    with patch(
        "agno_agent_os.coding_agent.subprocess.run",
        side_effect=FileNotFoundError("claude not found"),
    ):
        output, success = delegator._try_cli("claude", "do work")
    assert success is False
    assert "not found" in output.lower()


def test_try_cli_timeout():
    delegator = CLIDelegator()
    with patch(
        "agno_agent_os.coding_agent.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1),
    ):
        output, success = delegator._try_cli("claude", "do work")
    assert success is False
    assert "timed out" in output.lower()


# ---------------------------------------------------------------------------
# delegate tests
# ---------------------------------------------------------------------------


def test_delegate_with_mock():
    delegator = CLIDelegator()
    mock_completed = MagicMock()
    mock_completed.stdout = "feature done"
    mock_completed.stderr = ""
    mock_completed.returncode = 0
    with patch("agno_agent_os.coding_agent.subprocess.run", return_value=mock_completed) as mock_run:
        result = delegator.delegate("feature", "implement login")
    assert result == "feature done"
    mock_run.assert_called_once()
    # Verify the command used was claude (first in feature list)
    call_args = mock_run.call_args
    cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
    assert cmd[0] == "claude"


def test_delegate_fix_uses_codex():
    delegator = CLIDelegator()
    mock_completed = MagicMock()
    mock_completed.stdout = "fix applied"
    mock_completed.stderr = ""
    mock_completed.returncode = 0
    with patch("agno_agent_os.coding_agent.subprocess.run", return_value=mock_completed) as mock_run:
        result = delegator.delegate("fix", "fix memory leak")
    assert result == "fix applied"
    call_args = mock_run.call_args
    cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
    assert cmd[0] == "codex"


def test_delegate_refactor_uses_opencode():
    delegator = CLIDelegator()
    mock_completed = MagicMock()
    mock_completed.stdout = "refactored"
    mock_completed.stderr = ""
    mock_completed.returncode = 0
    with patch("agno_agent_os.coding_agent.subprocess.run", return_value=mock_completed) as mock_run:
        result = delegator.delegate("refactor", "simplify module")
    assert result == "refactored"
    call_args = mock_run.call_args
    cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
    assert cmd[0] == "opencode"


def test_delegate_fallback():
    """Primary CLI fails → fallback CLI is tried and succeeds."""
    delegator = CLIDelegator()

    # First call (claude) fails, second call (codex) succeeds
    fail_result = MagicMock()
    fail_result.stdout = ""
    fail_result.stderr = "claude error"
    fail_result.returncode = 1

    success_result = MagicMock()
    success_result.stdout = "codex output"
    success_result.stderr = ""
    success_result.returncode = 0

    with patch(
        "agno_agent_os.coding_agent.subprocess.run",
        side_effect=[fail_result, success_result],
    ) as mock_run:
        result = delegator.delegate("feature", "build feature X")

    assert result == "codex output"
    assert mock_run.call_count == 2
    # First call used claude, second used codex
    first_cmd = mock_run.call_args_list[0][0][0]
    second_cmd = mock_run.call_args_list[1][0][0]
    assert first_cmd[0] == "claude"
    assert second_cmd[0] == "codex"


def test_delegate_all_fail():
    """All CLIs fail → returns error string."""
    delegator = CLIDelegator()

    fail_result = MagicMock()
    fail_result.stdout = ""
    fail_result.stderr = "error"
    fail_result.returncode = 1

    with patch(
        "agno_agent_os.coding_agent.subprocess.run",
        side_effect=[
            fail_result,
            fail_result,
            fail_result,
        ],
    ):
        result = delegator.delegate("feature", "build feature X")

    assert "all CLIs failed" in result.lower() or "error" in result.lower()


def test_delegate_unknown_task_type():
    """Unknown task_type falls back to feature CLI list."""
    delegator = CLIDelegator()
    mock_completed = MagicMock()
    mock_completed.stdout = "output"
    mock_completed.stderr = ""
    mock_completed.returncode = 0
    with patch("agno_agent_os.coding_agent.subprocess.run", return_value=mock_completed):
        result = delegator.delegate("unknown_type", "do something")
    assert result == "output"