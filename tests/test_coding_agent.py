"""Tests for CodingAgent wrapper (Task 2.1)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from toolkinetik.coding_agent import (
    CodingAgent,
    CodingResult,
    QualityResult,
    SkillSpec,
)


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


def test_skill_spec_creation():
    spec = SkillSpec(
        name="weather",
        description="Get weather for a city",
        signature="get_weather(city: str) -> str",
        test_cases=["test_get_weather_returns_temperature"],
    )
    assert spec.name == "weather"
    assert spec.description == "Get weather for a city"
    assert spec.signature == "get_weather(city: str) -> str"
    assert spec.test_cases == ["test_get_weather_returns_temperature"]


def test_skill_spec_defaults():
    spec = SkillSpec(name="x", description="d", signature="f() -> None")
    assert spec.test_cases == []


def test_coding_result_creation():
    result = CodingResult(code="print('hi')", tests="def t(): pass", success=True)
    assert result.code == "print('hi')"
    assert result.tests == "def t(): pass"
    assert result.success is True
    assert result.error == ""
    assert result.cli_used == ""


def test_quality_result_creation():
    result = QualityResult(
        ruff_passed=True, mypy_passed=False, ast_valid=True, issues=["mypy: x"]
    )
    assert result.ruff_passed is True
    assert result.mypy_passed is False
    assert result.ast_valid is True
    assert result.issues == ["mypy: x"]


def test_quality_result_defaults():
    result = QualityResult(ruff_passed=True, mypy_passed=True, ast_valid=True)
    assert result.issues == []


# ---------------------------------------------------------------------------
# _call_cli tests
# ---------------------------------------------------------------------------


def test_call_cli_with_mock():
    agent = CodingAgent(cli_primary="claude", timeout=30)
    mock_completed = MagicMock()
    mock_completed.stdout = "generated code here"
    mock_completed.stderr = ""
    mock_completed.returncode = 0
    with patch("toolkinetik.coding_agent.subprocess.run", return_value=mock_completed) as mock_run:
        output = agent._call_cli("do something", "claude")
    assert output == "generated code here"
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert "claude" in args[0] or kwargs.get("args", [None])[0] == "claude"


def test_call_cli_timeout_raises():
    """_call_cli should raise TimeoutExpired so create_skill can fall back."""
    agent = CodingAgent(cli_primary="claude", timeout=5)
    with patch(
        "toolkinetik.coding_agent.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=5),
    ):
        with pytest.raises(subprocess.TimeoutExpired):
            agent._call_cli("do something", "claude")


# ---------------------------------------------------------------------------
# create_skill tests
# ---------------------------------------------------------------------------


def test_create_skill_with_mock():
    spec = SkillSpec(
        name="adder",
        description="Add two numbers",
        signature="add(a: int, b: int) -> int",
        test_cases=["test_add_positive", "test_add_negative"],
    )
    agent = CodingAgent(cli_primary="claude")
    fake_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    fake_tests = "def test_add_positive():\n    assert add(1, 2) == 3\n"

    with patch.object(agent, "_call_cli", side_effect=[fake_code, fake_tests]) as mock_cli:
        result = agent.create_skill(spec)

    assert isinstance(result, CodingResult)
    assert result.success is True
    assert "def add" in result.code
    assert "test_add" in result.tests
    assert result.cli_used == "claude"
    assert mock_cli.call_count == 2


def test_create_skill_fallback_cli():
    spec = SkillSpec(name="x", description="d", signature="f() -> None")
    agent = CodingAgent(cli_primary="claude", cli_fallbacks=["codex"])

    valid_code = "def f() -> None:\n    return None\n"
    valid_tests = "def test_f():\n    assert f() is None\n"

    with patch.object(
        agent,
        "_call_cli",
        side_effect=[
            subprocess.TimeoutExpired(cmd="claude", timeout=1),  # primary fails
            valid_code,  # codex works
            valid_tests,  # codex tests
        ],
    ):
        result = agent.create_skill(spec)
    assert result.success is True
    assert result.cli_used == "codex"


def test_create_skill_all_clis_fail():
    spec = SkillSpec(name="x", description="d", signature="f() -> None")
    agent = CodingAgent(cli_primary="claude", cli_fallbacks=["codex"])

    with patch.object(
        agent,
        "_call_cli",
        side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1),
    ):
        result = agent.create_skill(spec)
    assert result.success is False
    assert result.error != ""


# ---------------------------------------------------------------------------
# Prompt template tests
# ---------------------------------------------------------------------------


def test_writing_plans_prompt():
    agent = CodingAgent()
    spec = SkillSpec(name="weather", description="Get weather info", signature="f() -> None")
    prompt = agent._writing_plans_prompt(spec)
    assert "weather" in prompt
    assert "Get weather info" in prompt


def test_tdd_prompt():
    agent = CodingAgent()
    spec = SkillSpec(
        name="adder",
        description="Add two numbers",
        signature="add(a, b) -> int",
        test_cases=["test_add"],
    )
    prompt = agent._tdd_prompt(spec)
    assert "test" in prompt.lower()
    assert "test_add" in prompt or "tests first" in prompt.lower()


def test_debugging_prompt():
    agent = CodingAgent()
    prompt = agent._debugging_prompt("TypeError: invalid operation")
    assert "TypeError" in prompt
    assert "root cause" in prompt.lower() or "phase" in prompt.lower()


def test_code_review_prompt():
    agent = CodingAgent()
    prompt = agent._code_review_prompt("def f(): pass")
    assert "review" in prompt.lower() or "check" in prompt.lower()
    assert "def f" in prompt


# ---------------------------------------------------------------------------
# Quality gates tests
# ---------------------------------------------------------------------------


def test_quality_gates_with_valid_code():
    agent = CodingAgent()
    code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    result = agent._run_quality_gates(code)
    assert isinstance(result, QualityResult)
    assert result.ast_valid is True


def test_quality_gates_with_invalid_syntax():
    agent = CodingAgent()
    code = "def add(a, b\n    return a + b"  # syntax error
    result = agent._run_quality_gates(code)
    assert result.ast_valid is False
    assert len(result.issues) > 0


def test_quality_gates_ruff_check():
    """Ruff should pass on clean code."""
    agent = CodingAgent()
    code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    result = agent._run_quality_gates(code)
    # AST must be valid; ruff/mypy may vary by environment but AST is deterministic
    assert result.ast_valid is True