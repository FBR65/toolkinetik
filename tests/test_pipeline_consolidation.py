"""Tests for pipeline consolidation: legacy classes removed, SkillWriter delegates (#8).

SPEC: docs/SPEC-25-improvements.md #8
Tier 3 — SkillWriter uses TDDLoop/SkillPromoter, IntentDetector and
SkillCreationOrchestrator are removed.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "toolkinetik"


def _source(module: str) -> str:
    return (SRC / f"{module}.py").read_text()


class TestLegacyRemoved:
    def test_intent_detector_removed(self):
        src = _source("intent")
        assert not re.search(r"^class IntentDetector\b", src, re.MULTILINE), \
            "IntentDetector must be removed from intent.py"

    def test_skill_creation_orchestrator_removed(self):
        src = _source("intent")
        assert not re.search(r"^class SkillCreationOrchestrator\b", src, re.MULTILINE), \
            "SkillCreationOrchestrator must be removed from intent.py"

    def test_skill_writer_no_promoteresult_dataclass(self):
        src = _source("skill_writer")
        assert not re.search(r"^class PromoteResult\b", src, re.MULTILINE), \
            "skill_writer must not define its own PromoteResult (use promotion.PromotionResult)"

    def test_skill_writer_no_tddresult_dataclass(self):
        src = _source("skill_writer")
        assert not re.search(r"^class TDDResult\b", src, re.MULTILINE), \
            "skill_writer must not define its own TDDResult (use tdd_loop.TDDResult)"


class TestLegacyImportFails:
    def test_intent_detector_import_raises(self):
        with pytest.raises(ImportError):
            from toolkinetik.intent import IntentDetector  # noqa: F401

    def test_skill_creation_orchestrator_import_raises(self):
        with pytest.raises(ImportError):
            from toolkinetik.intent import SkillCreationOrchestrator  # noqa: F401


class TestCanonicalClassesAvailable:
    def test_promotion_result_importable(self):
        from toolkinetik.promotion import PromotionResult
        assert PromotionResult is not None

    def test_tdd_result_importable(self):
        from toolkinetik.tdd_loop import TDDResult
        assert TDDResult is not None

    def test_tdd_loop_runable_standalone(self):
        from toolkinetik.tdd_loop import TDDLoop, TDDResult
        sandbox = MagicMock()
        sandbox.run_tests.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}
        loop = TDDLoop(sandbox=sandbox)
        from toolkinetik.coding_agent import SkillSpec
        spec = SkillSpec(name="x", description="d", signature="def x():")
        result = loop.run(spec, "def x(): pass", "def t(): pass")
        assert isinstance(result, TDDResult)

    def test_skill_promoter_promote_standalone(self):
        import tempfile

        from toolkinetik.promotion import PromotionResult, SkillPromoter
        with tempfile.TemporaryDirectory() as tmp:
            promoter = SkillPromoter(
                skills_dir=tmp,
                registry=MagicMock(),
                db=MagicMock(),
            )
            with patch.object(promoter, "_git_commit", return_value=True):
                result = promoter.promote("test_skill", "def test_skill(): pass")
        assert isinstance(result, PromotionResult)


class TestSkillWriterDelegates:
    def test_skill_writer_uses_promotion_result(self):
        import tempfile

        # _promote should return a PromotionResult, not a local PromoteResult.
        from unittest.mock import MagicMock

        from toolkinetik.promotion import PromotionResult
        from toolkinetik.skill_writer import SkillWriter
        with tempfile.TemporaryDirectory() as tmp:
            writer = SkillWriter(registry=MagicMock(), db=MagicMock(), skills_dir=str(tmp))
            result = writer._promote("test_x", "def test_x(): pass")
        assert isinstance(result, PromotionResult), \
            f"_promote must return PromotionResult, got {type(result)}"