"""Tests for DB migration (P2.4) and skill rollback (P2.5).

SPEC: docs/SPEC-production-readiness.md P2.4-P2.5
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from toolkinetik.db import SkillStore
from toolkinetik.promotion import SkillPromoter


class TestDBMigration:
    """P2.4 — Schema version tracking in the database."""

    def test_db_has_schema_version_table(self, tmp_path: Path):
        """SkillStore creates a schema_version table."""
        SkillStore(str(tmp_path / "test.db"))
        import sqlite3
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        names = {t[0] for t in tables}
        assert "schema_version" in names

    def test_schema_version_starts_at_1(self, tmp_path: Path):
        """Fresh DB has schema_version = 1."""
        SkillStore(str(tmp_path / "test.db"))
        import sqlite3
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        version = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        conn.close()
        assert version is not None
        assert version[0] == 1


class TestSkillRollback:
    """P2.5 — Version tracking and rollback for promoted skills."""

    def test_promote_stores_version_in_db(self, tmp_path: Path):
        """Promotion stores the skill version in the DB."""
        registry = MagicMock()
        registry.get_tools.return_value = []
        db = SkillStore(str(tmp_path / "test.db"))
        promoter = SkillPromoter(skills_dir=str(tmp_path / "skills"), registry=registry, db=db)

        with patch.object(promoter, "_git_commit", return_value=True):
            promoter.promote("my_skill", "def my_skill(): return 1\n", {"version": "1.2.3"})

        skill = db.get_skill("my_skill")
        assert skill is not None
        assert skill["version"] == "1.2.3"

    def test_rollback_removes_skill(self, tmp_path: Path):
        """Rollback removes the skill file and marks it deleted in DB."""
        registry = MagicMock()
        registry.get_tools.return_value = []
        db = SkillStore(str(tmp_path / "test.db"))
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        promoter = SkillPromoter(skills_dir=str(skills_dir), registry=registry, db=db)

        with patch.object(promoter, "_git_commit", return_value=True):
            promoter.promote("temp_skill", "def temp_skill(): return 1\n")
        assert (skills_dir / "temp_skill.py").exists()

        ok = promoter.rollback("temp_skill")
        assert ok is True
        assert not (skills_dir / "temp_skill.py").exists()