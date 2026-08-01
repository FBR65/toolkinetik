"""Tests for the skill promotion & hot-reload pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agno_agent_os.promotion import SkillPromoter, PromotionResult


@pytest.fixture
def mock_registry() -> MagicMock:
    reg = MagicMock()
    reg.get_tools.return_value = []
    return reg


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    return db


@pytest.fixture
def promoter(tmp_path: Path, mock_registry: MagicMock, mock_db: MagicMock) -> SkillPromoter:
    return SkillPromoter(skills_dir=str(tmp_path), registry=mock_registry, db=mock_db)


class TestPromote:
    def test_promote_writes_file(self, promoter: SkillPromoter, tmp_path: Path):
        with patch.object(promoter, "_git_commit", return_value=True):
            result = promoter.promote("my_skill", "def foo(): return 42\n")
        assert (tmp_path / "my_skill.py").exists()
        assert (tmp_path / "my_skill.py").read_text() == "def foo(): return 42\n"
        assert result.skill_path == str(tmp_path / "my_skill.py")

    def test_promote_registers_in_db(self, promoter: SkillPromoter, mock_db: MagicMock):
        with patch.object(promoter, "_git_commit", return_value=True):
            promoter.promote("my_skill", "def foo(): return 42\n")
        assert mock_db.register_skill.called
        _args, kwargs = mock_db.register_skill.call_args
        name = _args[0] if _args else kwargs.get("name")
        assert name == "my_skill"

    def test_promote_triggers_reload(self, promoter: SkillPromoter, mock_registry: MagicMock):
        with patch.object(promoter, "_git_commit", return_value=True):
            promoter.promote("my_skill", "def foo(): return 42\n")
        assert mock_registry.get_tools.called

    def test_promote_success_result(self, promoter: SkillPromoter):
        with patch.object(promoter, "_git_commit", return_value=True):
            result = promoter.promote("my_skill", "def foo(): return 42\n")
        assert isinstance(result, PromotionResult)
        assert result.success is True
        assert result.git_committed is True
        assert result.error == ""


class TestRollback:
    def test_rollback_removes_file(self, promoter: SkillPromoter, tmp_path: Path):
        # First create the file via promote.
        with patch.object(promoter, "_git_commit", return_value=True):
            promoter.promote("my_skill", "def foo(): return 42\n")
        assert (tmp_path / "my_skill.py").exists()

        ok = promoter.rollback("my_skill")
        assert ok is True
        assert not (tmp_path / "my_skill.py").exists()

    def test_rollback_updates_db(self, promoter: SkillPromoter, mock_db: MagicMock):
        with patch.object(promoter, "_git_commit", return_value=True):
            promoter.promote("my_skill", "def foo(): return 42\n")
        promoter.rollback("my_skill")
        assert mock_db.delete_skill.called
        _args, _kw = mock_db.delete_skill.call_args
        assert _args[0] == "my_skill"

    def test_rollback_triggers_reload(self, promoter: SkillPromoter, mock_registry: MagicMock):
        with patch.object(promoter, "_git_commit", return_value=True):
            promoter.promote("my_skill", "def foo(): return 42\n")
        promoter.rollback("my_skill")
        # get_tools called at least once during rollback
        assert mock_registry.get_tools.called