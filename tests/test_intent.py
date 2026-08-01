"""Tests for intent detection & autonomous skill-creation — all deps mocked."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agno_agent_os.coding_agent import CodingResult, SkillSpec
from agno_agent_os.intent import IntentDetector, SkillCreationOrchestrator
from agno_agent_os.tdd_loop import TDDResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_registry(tool_names: list) -> MagicMock:
    """Build a mock DynamicToolRegistry that reports *tool_names*."""
    reg = MagicMock()
    tools = []
    for name in tool_names:
        fn = MagicMock()
        fn.__name__ = name
        tools.append(fn)
    reg.get_tools.return_value = tools
    return reg


# ---------------------------------------------------------------------------
# IntentDetector — detect_missing_skill
# ---------------------------------------------------------------------------


class TestDetectMissingSkill:
    def test_detector_no_missing_skill(self):
        """Request matches an existing tool → returns None."""
        reg = _mock_registry(["weather"])
        detector = IntentDetector(registry=reg)
        result = detector.detect_missing_skill("what is the weather today")
        assert result is None

    def test_detector_missing_skill(self):
        """Request doesn't match any tool → returns SkillSpec."""
        reg = _mock_registry(["weather"])
        detector = IntentDetector(registry=reg)
        result = detector.detect_missing_skill("convert PDF to markdown")
        assert result is not None
        assert isinstance(result, SkillSpec)
        assert result.name == "convert_pdf_to_markdown"

    def test_detector_no_registry(self):
        """With registry=None, always returns a SkillSpec (no tools to match)."""
        detector = IntentDetector(registry=None)
        result = detector.detect_missing_skill("calculate fibonacci")
        assert result is not None
        assert isinstance(result, SkillSpec)


# ---------------------------------------------------------------------------
# IntentDetector — _extract_skill_name
# ---------------------------------------------------------------------------


class TestExtractSkillName:
    def test_extract_skill_name_pdf(self):
        detector = IntentDetector()
        assert detector._extract_skill_name("PDF to markdown") == "pdf_to_markdown"

    def test_extract_skill_name_calc(self):
        detector = IntentDetector()
        assert detector._extract_skill_name("calculate fibonacci") == "calculate_fibonacci"


# ---------------------------------------------------------------------------
# IntentDetector — _match_tools
# ---------------------------------------------------------------------------


class TestMatchTools:
    def test_match_tools_found(self):
        detector = IntentDetector()
        assert detector._match_tools("check the weather", ["weather"]) is True

    def test_match_tools_not_found(self):
        detector = IntentDetector()
        assert detector._match_tools("convert PDF to markdown", ["weather"]) is False

    def test_match_tools_empty(self):
        detector = IntentDetector()
        assert detector._match_tools("do something", []) is False

    def test_match_tools_multi_word(self):
        detector = IntentDetector()
        assert detector._match_tools("send an email", ["send_email"]) is True


# ---------------------------------------------------------------------------
# SkillCreationOrchestrator
# ---------------------------------------------------------------------------


class TestOrchestrator:
    def test_orchestrator_skill_exists(self):
        """Detector returns None → 'already exists' message, no creation."""
        detector = MagicMock()
        detector.detect_missing_skill.return_value = None

        coding_agent = MagicMock()
        sandbox = MagicMock()
        promoter = MagicMock()
        tdd_loop = MagicMock()

        orch = SkillCreationOrchestrator(detector, coding_agent, sandbox, promoter, tdd_loop)
        msg = orch.handle_request("check weather")

        assert "already exists" in msg
        coding_agent.create_skill.assert_not_called()
        tdd_loop.run.assert_not_called()
        promoter.promote.assert_not_called()

    def test_orchestrator_creates_skill(self):
        """Full flow: detect → create → TDD → promote → success message."""
        spec = SkillSpec(
            name="fibonacci",
            description="calculate fibonacci",
            signature="def fibonacci(n: int) -> int",
            test_cases=["fibonacci(0) == 0"],
        )
        detector = MagicMock()
        detector.detect_missing_skill.return_value = spec

        coding_result = CodingResult(
            code="def fibonacci(n): ...",
            tests="def test_fib(): ...",
            success=True,
            cli_used="claude",
        )
        coding_agent = MagicMock()
        coding_agent.create_skill.return_value = coding_result

        tdd_result = TDDResult(
            success=True,
            exit_code=0,
            stdout="1 passed",
            stderr="",
            security_passed=True,
            attempts=1,
        )
        tdd_loop = MagicMock()
        tdd_loop.run.return_value = tdd_result

        promo_result = MagicMock()
        promo_result.success = True
        promo_result.git_committed = True
        promo_result.error = ""
        promoter = MagicMock()
        promoter.promote.return_value = promo_result

        sandbox = MagicMock()

        orch = SkillCreationOrchestrator(detector, coding_agent, sandbox, promoter, tdd_loop)
        msg = orch.handle_request("calculate fibonacci")

        detector.detect_missing_skill.assert_called_once_with("calculate fibonacci")
        coding_agent.create_skill.assert_called_once_with(spec)
        tdd_loop.run.assert_called_once()
        promoter.promote.assert_called_once()
        assert "successfully" in msg

    def test_orchestrator_coding_fails(self):
        """CodingAgent returns success=False → failure message, no TDD/promote."""
        spec = SkillSpec(
            name="badskill",
            description="bad",
            signature="def badskill():",
            test_cases=[],
        )
        detector = MagicMock()
        detector.detect_missing_skill.return_value = spec

        coding_result = CodingResult(
            code="",
            tests="",
            success=False,
            error="CLI failed",
        )
        coding_agent = MagicMock()
        coding_agent.create_skill.return_value = coding_result

        tdd_loop = MagicMock()
        promoter = MagicMock()
        sandbox = MagicMock()

        orch = SkillCreationOrchestrator(detector, coding_agent, sandbox, promoter, tdd_loop)
        msg = orch.handle_request("make a badskill")

        assert "failed" in msg
        tdd_loop.run.assert_not_called()
        promoter.promote.assert_not_called()

    def test_orchestrator_tdd_fails(self):
        """TDD loop returns success=False → failure message, no promote."""
        spec = SkillSpec(
            name="failskill",
            description="fail",
            signature="def failskill():",
            test_cases=[],
        )
        detector = MagicMock()
        detector.detect_missing_skill.return_value = spec

        coding_result = CodingResult(
            code="def failskill(): pass",
            tests="def test_fail(): assert False",
            success=True,
        )
        coding_agent = MagicMock()
        coding_agent.create_skill.return_value = coding_result

        tdd_result = TDDResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="assert error",
            security_passed=False,
            attempts=3,
            error="tests failed",
        )
        tdd_loop = MagicMock()
        tdd_loop.run.return_value = tdd_result

        promoter = MagicMock()
        sandbox = MagicMock()

        orch = SkillCreationOrchestrator(detector, coding_agent, sandbox, promoter, tdd_loop)
        msg = orch.handle_request("make a failskill")

        assert "failed" in msg
        promoter.promote.assert_not_called()