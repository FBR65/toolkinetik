"""Tests for SkillWriter._revise_code signature and safety recheck (#4).

SPEC: docs/SPEC-25-improvements.md #4
Tier 2 — _revise_code must take only (code, error_trace); revised code
must be safety-checked before being used in the retry loop.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

from toolkinetik.skill_writer import SkillWriter


def _make_writer(tmp_path) -> SkillWriter:
    return SkillWriter(
        wigolo=None,
        llm=MagicMock(),
        sandbox=MagicMock(),
        registry=MagicMock(),
        db=MagicMock(),
        skills_dir=str(tmp_path),
        max_retries=3,
    )


class TestReviseCodeSignature:
    def test_revise_code_has_two_params(self):
        sig = inspect.signature(SkillWriter._revise_code)
        params = list(sig.parameters.keys())
        # self, code, error_trace  — no spec_name
        assert "spec_name" not in params
        assert "code" in params
        assert "error_trace" in params
        assert len(params) == 3  # self + code + error_trace


class TestReviseCodeCalledCorrectly:
    def test_revise_code_called_with_code_and_error_trace(self, tmp_path):
        writer = _make_writer(tmp_path)
        # First sandbox run fails with ImportError, then succeeds.
        writer._sandbox.run_tests.side_effect = [
            {"exit_code": 1, "stdout": "ImportError: no module", "stderr": "err"},
            {"exit_code": 0, "stdout": "ok", "stderr": ""},
        ]
        writer._llm.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="```python\ndef fixed(): pass\n```"))
        ]
        with patch.object(writer, "_revise_code", wraps=writer._revise_code) as spy:
            writer._run_tdd("original code", "tests")
        # spy was called; check it got code + error_trace (not spec_name=code)
        assert spy.called
        call_args = spy.call_args
        # positional: (code, error_trace)
        assert call_args.args[0] == "original code"
        assert "ImportError" in call_args.args[1] or "ImportError" in str(call_args.args[1])

    def test_revised_code_safety_checked(self, tmp_path):
        writer = _make_writer(tmp_path)
        # sandbox fails first, then succeeds
        writer._sandbox.run_tests.side_effect = [
            {"exit_code": 1, "stdout": "fail", "stderr": "err"},
            {"exit_code": 0, "stdout": "ok", "stderr": ""},
        ]
        # LLM returns revised code that imports os (forbidden)
        writer._llm.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="```python\nimport os\ndef bad(): pass\n```"))
        ]
        with patch.object(writer, "_safety_check", wraps=writer._safety_check) as spy_safety:
            result = writer._run_tdd("original", "tests")
        # The revised code was safety-checked
        assert spy_safety.called
        # Result must be failure because safety check failed on revised code
        assert result.success is False


class TestNoStdinToError:
    def test_stdin_to_error_removed(self):
        from toolkinetik import skill_writer
        assert not hasattr(skill_writer, "stdin_to_error")