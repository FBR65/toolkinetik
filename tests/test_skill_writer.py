"""Tests for the SkillWriterSkill (TDD: RED phase)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from toolkinetik.coding_agent import SkillSpec
from toolkinetik.safety import SafetyReport
from toolkinetik.skill_writer import SkillWriter, SkillWriterResult
from toolkinetik.tdd_loop import TDDResult


class TestSkillSpecGeneration:
    """SkillWriter: generate SkillSpec from natural language."""

    def test_spec_from_simple_request(self):
        """Heuristic name extraction filters stopwords like 'a', 'the'."""
        writer = SkillWriter(wigolo=MagicMock(), llm=MagicMock())
        spec = writer.generate_spec("Create a presentation")
        assert spec.name == "create_presentation"

    def test_spec_from_math_request(self):
        writer = SkillWriter(wigolo=MagicMock(), llm=MagicMock())
        spec = writer.generate_spec("Calculate the nth prime number")
        assert "prime" in spec.name.lower()


class TestWigoloResearch:
    """SkillWriter: wigolo research integration."""

    def test_wigolo_research_called_with_package_name(self):
        wigolo = MagicMock()
        wigolo.research.return_value = {"results": [{"content": "pptx.Presentation()"}]}
        writer = SkillWriter(wigolo=wigolo, llm=MagicMock())
        spec = SkillSpec(name="powerpoint", description="test", signature="def test():")
        writer._research_dependencies(spec)
        wigolo.research.assert_called_once()
        call_kwargs = wigolo.research.call_args.kwargs
        assert "powerpoint" in call_kwargs.get("query", "").lower()


class TestSafetyCheck:
    """SkillWriter: SafetyChecker rejects dangerous code."""

    def test_forbidden_import_subprocess(self):
        code = """
import subprocess
def foo():
    pass
"""
        writer = SkillWriter(wigolo=MagicMock(), llm=MagicMock())
        result = writer._safety_check(code)
        assert not result.passed
        assert any("subprocess" in issue for issue in result.issues)

    def test_forbidden_call_os_system(self):
        code = """
import os
def foo():
    os.system("rm -rf /")
"""
        writer = SkillWriter(wigolo=MagicMock(), llm=MagicMock())
        result = writer._safety_check(code)
        assert not result.passed
        assert any("os.system" in issue for issue in result.issues)

    def test_safe_code_passes(self):
        code = """
def calculate_sum(a: int, b: int) -> int:
    return a + b
"""
        writer = SkillWriter(wigolo=MagicMock(), llm=MagicMock())
        result = writer._safety_check(code)
        assert result.passed


class TestTDDLoopIntegration:
    """SkillWriter: Docker sandbox TDD integration."""

    def test_tdd_loop_invoked_with_code_and_tests(self):
        sandbox = MagicMock()
        sandbox.run_tests.return_value = {"exit_code": 0, "stdout": "1 passed", "stderr": ""}
        writer = SkillWriter(wigolo=MagicMock(), llm=MagicMock(), sandbox=sandbox)
        code = "def foo(): return 42"
        tests = "def test_foo(): assert foo() == 42"
        result = writer._run_tdd(code, tests)
        sandbox.run_tests.assert_called_once()
        assert result.exit_code == 0


class TestPromotion:
    """SkillWriter: promote generated skill."""

    def test_promote_writes_skill_file(self, tmp_path):
        registry = MagicMock()
        registry.get_tools.return_value = []
        db = MagicMock()
        writer = SkillWriter(wigolo=MagicMock(), llm=MagicMock(), registry=registry, db=db, skills_dir=str(tmp_path))
        code = "def test_func(): return 1"
        result = writer._promote("test_func", code, {}, commit=False)
        assert result.success
        skill_file = tmp_path / "test_func.py"
        assert skill_file.exists()
        assert "def test_func" in skill_file.read_text()

    def test_promote_triggers_hot_reload(self, tmp_path):
        registry = MagicMock()
        registry.get_tools.return_value = []
        db = MagicMock()
        writer = SkillWriter(wigolo=MagicMock(), llm=MagicMock(), registry=registry, db=db, skills_dir=str(tmp_path))
        writer._promote("test_func", "def test_func(): pass", {}, commit=False)
        registry.get_tools.assert_called()


class TestFullFlow:
    """SkillWriter: end-to-end write_skill."""

    def test_write_skill_returns_result(self):
        writer = SkillWriter(wigolo=MagicMock(), llm=MagicMock())
        with patch.object(writer, "_research_dependencies"), \
             patch.object(writer, "_generate_code", return_value=("def foo(): return 1", "def test_foo(): pass")), \
             patch.object(writer, "_run_tdd", return_value=TDDResult(success=True, exit_code=0, stdout="passed", stderr="", security_passed=True, attempts=1)), \
             patch.object(writer, "_safety_check") as mock_safety, \
             patch.object(writer, "_promote") as mock_promote:
            mock_safety.return_value = SafetyReport(passed=True)
            promo_result = MagicMock()
            promo_result.success = True
            mock_promote.return_value = promo_result
            result = writer.write_skill("Create a powerpoint presentation")
            assert isinstance(result, SkillWriterResult)
            assert result.success
