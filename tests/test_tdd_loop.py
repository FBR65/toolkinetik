"""Tests for the automated TDD loop — sandbox is mocked."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from toolkinetik.coding_agent import SkillSpec
from toolkinetik.tdd_loop import TDDLoop, TDDResult, SecurityResult


def _make_sandbox(exit_code: int = 0, stdout: str = "1 passed", stderr: str = "") -> MagicMock:
    sb = MagicMock()
    sb.run_tests.return_value = {"exit_code": exit_code, "stdout": stdout, "stderr": stderr}
    return sb


def _spec() -> SkillSpec:
    return SkillSpec(
        name="adder",
        description="adds two numbers",
        signature="def add(a: int, b: int) -> int",
        test_cases=["adds 1 + 2 == 3"],
    )


CLEAN_CODE = "def add(a, b):\n    return a + b\n"
CODE_OS_SYSTEM = "import os\n\ndef add(a, b):\n    os.system('rm -rf /')\n    return a + b\n"
CODE_EVAL = "def add(a, b):\n    return eval('a+b')\n"
CODE_EXEC = "def add(a, b):\n    exec('print(1)')\n    return a + b\n"


class TestTDDLoopSuccess:
    def test_tdd_loop_success(self):
        sb = _make_sandbox(exit_code=0, stdout="1 passed")
        loop = TDDLoop(sb, max_retries=3)
        result = loop.run(_spec(), CLEAN_CODE, "def test_add(): assert add(1,2)==3")
        assert isinstance(result, TDDResult)
        assert result.success is True
        assert result.exit_code == 0
        assert result.security_passed is True
        assert result.attempts == 1


class TestTDDLoopFailure:
    def test_tdd_loop_test_failure(self):
        sb = _make_sandbox(exit_code=1, stdout="", stderr="AssertionError: boom")
        loop = TDDLoop(sb, max_retries=3)
        result = loop.run(_spec(), CLEAN_CODE, "def test_add(): assert False")
        assert result.success is False
        assert result.exit_code == 1
        assert result.attempts == 3  # exhausted retries


class TestSecurityCheck:
    def test_tdd_loop_security_clean(self):
        sb = _make_sandbox(exit_code=0, stdout="1 passed")
        loop = TDDLoop(sb, max_retries=3)
        result = loop.run(_spec(), CLEAN_CODE, "def test_add(): assert True")
        assert result.security_passed is True
        assert result.security_issues == []

    def test_tdd_loop_security_os_system(self):
        sb = _make_sandbox(exit_code=0, stdout="1 passed")
        loop = TDDLoop(sb, max_retries=3)
        result = loop.run(_spec(), CODE_OS_SYSTEM, "def test_add(): assert True")
        assert result.security_passed is False
        assert any("os.system" in i or "os.system" in str(i) for i in result.security_issues)

    def test_tdd_loop_security_eval(self):
        sb = _make_sandbox(exit_code=0, stdout="1 passed")
        loop = TDDLoop(sb, max_retries=3)
        result = loop.run(_spec(), CODE_EVAL, "def test_add(): assert True")
        assert result.security_passed is False

    def test_tdd_loop_security_exec(self):
        sb = _make_sandbox(exit_code=0, stdout="1 passed")
        loop = TDDLoop(sb, max_retries=3)
        result = loop.run(_spec(), CODE_EXEC, "def test_add(): assert True")
        assert result.security_passed is False


class TestRetries:
    def test_tdd_loop_retry_count(self):
        # First two attempts fail, third succeeds.
        sb = MagicMock()
        sb.run_tests.side_effect = [
            {"exit_code": 1, "stdout": "", "stderr": "fail 1"},
            {"exit_code": 1, "stdout": "", "stderr": "fail 2"},
            {"exit_code": 0, "stdout": "1 passed", "stderr": ""},
        ]
        loop = TDDLoop(sb, max_retries=3)
        result = loop.run(_spec(), CLEAN_CODE, "def test_add(): assert True")
        assert result.success is True
        assert result.attempts == 3

    def test_tdd_loop_max_retries(self):
        sb = _make_sandbox(exit_code=1, stdout="", stderr="always fails")
        loop = TDDLoop(sb, max_retries=3)
        result = loop.run(_spec(), CLEAN_CODE, "def test_add(): assert False")
        assert result.success is False
        assert result.attempts == 3
        assert sb.run_tests.call_count == 3