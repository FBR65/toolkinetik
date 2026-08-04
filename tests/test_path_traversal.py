"""Tests for path-traversal protection in skill promotion (#1).

SPEC: docs/SPEC-25-improvements.md #1
Tier 3 — Security: skill_name with `../` or absolute paths must be rejected
before any file write, DB registration, or hot-reload is attempted.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from toolkinetik.promotion import SkillPromoter
from toolkinetik.skill_writer import SkillWriter


@pytest.fixture
def mock_registry() -> MagicMock:
    reg = MagicMock()
    reg.get_tools.return_value = []
    return reg


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def promoter(tmp_path: Path, mock_registry: MagicMock, mock_db: MagicMock) -> SkillPromoter:
    return SkillPromoter(skills_dir=str(tmp_path), registry=mock_registry, db=mock_db)


@pytest.fixture
def writer(tmp_path: Path, mock_registry: MagicMock, mock_db: MagicMock) -> SkillWriter:
    return SkillWriter(registry=mock_registry, db=mock_db, skills_dir=str(tmp_path))


class TestPromoterPathTraversal:
    def test_relative_traversal_rejected(self, promoter: SkillPromoter, tmp_path: Path):
        result = promoter.promote("../evil", "pass\n")
        assert result.success is False
        assert "traversal" in result.error.lower()
        assert not (tmp_path.parent / "evil.py").exists()

    def test_double_dot_slash_rejected(self, promoter: SkillPromoter, tmp_path: Path):
        result = promoter.promote("../../etc/evil", "pass\n")
        assert result.success is False
        assert "traversal" in result.error.lower()

    def test_absolute_path_rejected(self, promoter: SkillPromoter, tmp_path: Path):
        abs_name = os.path.join(os.path.dirname(str(tmp_path)), "abs_skill")
        result = promoter.promote(abs_name, "pass\n")
        assert result.success is False
        assert "traversal" in result.error.lower()
        assert not Path(abs_name + ".py").exists()

    def test_traversal_skips_db_and_reload(self, promoter: SkillPromoter, mock_db: MagicMock, mock_registry: MagicMock):
        result = promoter.promote("../evil", "pass\n")
        assert result.success is False
        assert not mock_db.register_skill.called
        assert not mock_registry.get_tools.called

    def test_valid_name_still_works(self, promoter: SkillPromoter, tmp_path: Path):
        with patch.object(promoter, "_git_commit", return_value=True):
            result = promoter.promote("my_skill", "def my_skill(): pass\n")
        assert result.success is True
        assert (tmp_path / "my_skill.py").exists()

    def test_rollback_traversal_rejected(self, promoter: SkillPromoter, tmp_path: Path):
        ok = promoter.rollback("../evil")
        assert ok is False
        assert not (tmp_path.parent / "evil.py").exists()


class TestSkillWriterPathTraversal:
    def test_writer_promote_traversal_rejected(self, writer: SkillWriter, tmp_path: Path):
        result = writer._promote("../bad", "pass\n")
        assert result.success is False
        assert "traversal" in result.error.lower()
        assert not (tmp_path.parent / "bad.py").exists()

    def test_writer_promote_absolute_rejected(self, writer: SkillWriter, tmp_path: Path):
        abs_name = os.path.join(os.path.dirname(str(tmp_path)), "abs_writer")
        result = writer._promote(abs_name, "pass\n")
        assert result.success is False
        assert "traversal" in result.error.lower()

    def test_writer_promote_valid_still_works(self, writer: SkillWriter, tmp_path: Path):
        result = writer._promote("good_skill", "def good_skill(): pass\n")
        assert result.success is True
        assert (tmp_path / "good_skill.py").exists()