"""Additional tests for skill_writer.py coverage (P3.3).

SPEC: docs/SPEC-production-readiness.md P3.3
Covers _run_local_tdd, _llm_classify JSONDecodeError fallback, _stub_code paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from toolkinetik.coding_agent import SkillSpec
from toolkinetik.skill_writer import SkillWriter


class TestRunLocalTdd:
    def test_run_local_tdd_success(self):
        """_run_local_tdd runs pytest locally and succeeds on valid code."""
        writer = SkillWriter(llm=None)
        code = "def add(a, b): return a + b\n"
        tests = "from skill import add\ndef test_add(): assert add(1, 2) == 3\n"
        result = writer._run_local_tdd(code, tests)
        assert result.success is True
        assert result.exit_code == 0

    def test_run_local_tdd_failure(self):
        """_run_local_tdd fails when tests fail."""
        writer = SkillWriter(llm=None)
        code = "def add(a, b): return a - b\n"  # wrong
        tests = "from skill import add\ndef test_add(): assert add(1, 2) == 3\n"
        result = writer._run_local_tdd(code, tests)
        assert result.success is False
        assert result.exit_code != 0


class TestLlmClassifyFallback:
    def test_llm_classify_json_decode_error_returns_empty(self):
        """_llm_classify returns {} on JSONDecodeError."""
        llm = MagicMock()
        llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="not valid json"))]
        )
        writer = SkillWriter(llm=llm)
        result = writer._llm_classify("test request")
        assert result == {}

    def test_llm_classify_missing_name_uses_heuristic(self):
        """generate_spec falls back to heuristic name when LLM returns no name."""
        llm = MagicMock()
        llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"description": "a test"}'))]
        )
        writer = SkillWriter(llm=llm)
        spec = writer.generate_spec("create a calculator")
        assert spec.name == "create_calculator"

    def test_llm_classify_valid_json(self):
        """_llm_classify parses valid JSON correctly."""
        llm = MagicMock()
        llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"name": "my_func", "description": "test", "signature": "def my_func()"}'))]
        )
        writer = SkillWriter(llm=llm)
        result = writer._llm_classify("test")
        assert result["name"] == "my_func"
        assert result["description"] == "test"


class TestStubCodePaths:
    def test_stub_code_is_ast_valid(self):
        """_stub_code produces AST-valid Python."""
        writer = SkillWriter(llm=None)
        import ast
        spec = SkillSpec(name="my_skill", description="test", signature="def my_skill():")
        code = writer._stub_code(spec)
        ast.parse(code)  # should not raise

    def test_stub_tests_reference_skill_name(self):
        """_stub_tests imports the skill by name."""
        writer = SkillWriter(llm=None)
        spec = SkillSpec(name="fibonacci", description="test", signature="def fibonacci():")
        tests = writer._stub_tests(spec)
        assert "from skill import fibonacci" in tests
        assert "fibonacci()" in tests


class TestParseCodeAndTests:
    def test_parse_two_blocks(self):
        """_parse_code_and_tests extracts code and test from two ```python blocks."""
        writer = SkillWriter(llm=None)
        raw = "```python\ndef test_x(): assert True\n```\n```python\ndef x(): return 1\n```"
        code, tests = writer._parse_code_and_tests(raw)
        assert "def x()" in code
        assert "def test_x()" in tests

    def test_parse_one_block(self):
        """_parse_code_and_tests with one block returns it as code."""
        writer = SkillWriter(llm=None)
        raw = "```python\ndef x(): return 1\n```"
        code, tests = writer._parse_code_and_tests(raw)
        assert "def x()" in code
        assert tests == ""

    def test_parse_no_blocks(self):
        """_parse_code_and_tests with no blocks returns empty strings."""
        writer = SkillWriter(llm=None)
        code, tests = writer._parse_code_and_tests("no code here")
        assert code == ""
        assert tests == ""


class TestResearchDependencies:
    def test_research_no_wigolo_returns_empty(self):
        """_research_dependencies returns empty string when wigolo is None."""
        writer = SkillWriter(wigolo=None, llm=None)
        spec = SkillSpec(name="test", description="test", signature="def test():")
        result = writer._research_dependencies(spec)
        assert result == ""

    def test_research_wigolo_exception_returns_empty(self):
        """_research_dependencies returns empty string when wigolo raises."""
        wigolo = MagicMock()
        wigolo.research.side_effect = Exception("network error")
        writer = SkillWriter(wigolo=wigolo, llm=None)
        spec = SkillSpec(name="test", description="test", signature="def test():")
        result = writer._research_dependencies(spec)
        assert result == ""