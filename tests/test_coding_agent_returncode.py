"""Tests for CodingAgent._call_cli return-code handling (#5).

SPEC: docs/SPEC-25-improvements.md #5
Tier 3 — a CLI failure (returncode != 0) must NOT be returned as if it were
valid code output; it must raise so callers fall back. Empty output on
success must also raise.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from toolkinetik.coding_agent import CodingAgent, SkillSpec


def _mock_completed(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


class TestCallCliReturnCode:
    def test_nonzero_returncode_raises_runtime_error(self):
        agent = CodingAgent(cli_primary="claude")
        with patch("toolkinetik.coding_agent.subprocess.run",
                   return_value=_mock_completed(1, stdout="", stderr="boom")):
            with pytest.raises(RuntimeError, match="boom"):
                agent._call_cli("prompt", "claude")

    def test_nonzero_returncode_includes_stderr_in_message(self):
        agent = CodingAgent(cli_primary="claude")
        with patch("toolkinetik.coding_agent.subprocess.run",
                   return_value=_mock_completed(2, stdout="", stderr="compile error here")):
            with pytest.raises(RuntimeError, match="compile error here"):
                agent._call_cli("prompt", "claude")

    def test_zero_returncode_empty_stdout_raises(self):
        agent = CodingAgent(cli_primary="claude")
        with patch("toolkinetik.coding_agent.subprocess.run",
                   return_value=_mock_completed(0, stdout="", stderr="")):
            with pytest.raises(ValueError, match="empty"):
                agent._call_cli("prompt", "claude")

    def test_zero_returncode_nonempty_stdout_returns_stdout(self):
        agent = CodingAgent(cli_primary="claude")
        with patch("toolkinetik.coding_agent.subprocess.run",
                   return_value=_mock_completed(0, stdout="def foo(): pass\n", stderr="")):
            out = agent._call_cli("prompt", "claude")
        assert out == "def foo(): pass\n"

    def test_create_skill_all_clis_fail_code_empty(self):
        """All CLIs failing must yield CodingResult.code == '' (no stderr leaked)."""
        spec = SkillSpec(name="x", description="d", signature="f() -> None")
        agent = CodingAgent(cli_primary="claude", cli_fallbacks=["codex"])
        with patch("toolkinetik.coding_agent.subprocess.run",
                   return_value=_mock_completed(1, stdout="", stderr="command not found")):
            result = agent.create_skill(spec)
        assert result.success is False
        assert result.code == ""
        assert "command not found" in result.error

    def test_create_skill_falls_back_on_nonzero(self):
        """A failing primary CLI (nonzero) should fall through to the next."""
        spec = SkillSpec(name="x", description="d", signature="f() -> None")
        agent = CodingAgent(cli_primary="claude", cli_fallbacks=["codex"])
        good_code = "def f() -> None:\n    return None\n"
        good_tests = "def test_f():\n    assert f() is None\n"
        # First call: claude nonzero → raise → fall back.
        # Then codex success for code, then codex success for tests.
        runs = [
            _mock_completed(1, stdout="", stderr="claude broken"),
            _mock_completed(0, stdout=good_code, stderr=""),
            _mock_completed(0, stdout=good_tests, stderr=""),
        ]
        with patch("toolkinetik.coding_agent.subprocess.run",
                   side_effect=runs):
            result = agent.create_skill(spec)
        assert result.success is True
        assert result.cli_used == "codex"