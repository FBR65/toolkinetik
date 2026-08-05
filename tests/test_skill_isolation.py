"""Tests for skill isolation via subprocess (P1.6).

SPEC: docs/SPEC-production-readiness.md P1.6
Skills must execute in an isolated worker process with timeout and memory
limits, so a buggy skill can't crash the main server.
"""

from __future__ import annotations

import pytest

from toolkinetik.skill_runner import SkillRunner


@pytest.fixture
def runner() -> SkillRunner:
    return SkillRunner(timeout=10, memory_mb=256)


class TestSkillRunner:
    def test_runner_exists(self):
        """SkillRunner can be instantiated."""
        r = SkillRunner()
        assert r is not None

    def test_run_simple_skill_returns_result(self, runner: SkillRunner):
        """A simple skill function runs and returns its result."""
        code = """
def add(a, b):
    return a + b
print(add(2, 3))
"""
        result = runner.run_code(code)
        assert result["exit_code"] == 0
        assert "5" in result["stdout"]

    def test_run_skill_with_timeout(self):
        """A skill that runs forever is killed by the timeout."""
        runner = SkillRunner(timeout=2, memory_mb=256)
        code = """
while True:
    pass
"""
        result = runner.run_code(code)
        assert result["exit_code"] != 0
        assert "timeout" in result["stderr"].lower() or result["exit_code"] == -9

    def test_skill_exception_captured(self, runner: SkillRunner):
        """A skill that raises an exception is captured, not crashing the runner."""
        code = """
raise ValueError("skill bug")
"""
        result = runner.run_code(code)
        assert result["exit_code"] != 0
        assert "ValueError" in result["stderr"] or "skill bug" in result["stderr"]

    def test_runner_isolates_memory(self, runner: SkillRunner):
        """The runner process is separate from the main process."""
        code = """
import os
print(f"pid={os.getpid()}")
"""
        result = runner.run_code(code)
        assert result["exit_code"] == 0
        # The PID in the output should be different from the current process
        import os
        current_pid = os.getpid()
        assert f"pid={current_pid}" not in result["stdout"], \
            "skill ran in the main process, not isolated"

    def test_run_function_with_single_quote_in_arg(self, runner: SkillRunner):
        """run_function must handle args containing single quotes without syntax errors.

        Regression: json.dumps produces unescaped single quotes inside a
        Python single-quoted string literal, causing SyntaxError.
        """
        code = "def echo(text):\n    return text\n"
        result = runner.run_function(code, "echo", "it's working")
        assert result["exit_code"] == 0

    def test_run_function_with_double_quote_in_arg(self, runner: SkillRunner):
        """run_function must handle args containing double quotes."""
        code = "def echo(text):\n    return text\n"
        result = runner.run_function(code, "echo", 'he said "hi"')
        assert result["exit_code"] == 0

    def test_run_function_with_keyword_args(self, runner: SkillRunner):
        """run_function passes keyword arguments correctly."""
        code = "def greet(greeting, name):\n    return f'{greeting}, {name}'\n"
        result = runner.run_function(code, "greet", greeting="Hello", name="World")
        assert result["exit_code"] == 0