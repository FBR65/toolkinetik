"""Skill promotion & hot-reload pipeline with git-based rollback.

Task 3.3: SkillPromoter writes a generated skill to the skills directory,
triggers the DynamicToolRegistry hot-reload, registers metadata in the
SQLite SkillStore, and commits the change to git.  Rollback removes the
file, marks the DB row as deleted, and re-triggers hot-reload.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from toolkinetik.config import get_settings
from toolkinetik.db import SkillStore
from toolkinetik.registry import DynamicToolRegistry


@dataclass
class PromotionResult:
    """Outcome of a promotion attempt."""

    success: bool
    skill_path: str = ""
    error: str = ""
    git_committed: bool = False


class SkillPromoter:
    """Promote generated skills to the live registry and commit to git."""

    def __init__(
        self,
        skills_dir: Optional[str] = None,
        registry: Optional[DynamicToolRegistry] = None,
        db: Optional[SkillStore] = None,
    ) -> None:
        settings = get_settings()
        self.skills_dir = skills_dir if skills_dir is not None else str(settings.skills_path)
        self.registry = registry if registry is not None else DynamicToolRegistry(self.skills_dir)
        self.db = db if db is not None else SkillStore(str(settings.db_full_path)
                                                       )
        # Ensure the directory exists.
        Path(self.skills_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def promote(
        self,
        skill_name: str,
        code: str,
        metadata: Optional[dict] = None,
    ) -> PromotionResult:
        """Write *code* to ``<skills_dir>/<skill_name>.py`` and register it."""
        skill_path = Path(self.skills_dir) / f"{skill_name}.py"
        try:
            skill_path.write_text(code)
        except OSError as exc:
            return PromotionResult(success=False, error=f"write failed: {exc}")

        # Trigger hot-reload.
        try:
            self.registry.get_tools()
        except Exception as exc:  # pragma: no cover - defensive
            return PromotionResult(
                success=False,
                skill_path=str(skill_path),
                error=f"hot-reload failed: {exc}",
            )

        # Register metadata in the DB.
        meta = metadata or {}
        try:
            self.db.register_skill(
                name=skill_name,
                module=skill_name,
                function=meta.get("function", skill_name),
                description=meta.get("description", ""),
                signature=meta.get("signature", ""),
                version=meta.get("version", "1.0.0"),
                created_by=meta.get("created_by", ""),
                git_commit="",
            )
        except Exception as exc:  # pragma: no cover - defensive
            return PromotionResult(
                success=False,
                skill_path=str(skill_path),
                error=f"db register failed: {exc}",
            )

        # Git commit.
        git_ok = self._git_commit(skill_path)

        return PromotionResult(
            success=True,
            skill_path=str(skill_path),
            error="",
            git_committed=git_ok,
        )

    def rollback(self, skill_name: str) -> bool:
        """Remove the skill file, mark DB row deleted, and hot-reload."""
        skill_path = Path(self.skills_dir) / f"{skill_name}.py"
        try:
            if skill_path.exists():
                skill_path.unlink()
        except OSError:
            return False

        try:
            self.db.delete_skill(skill_name)
        except Exception:
            # DB may not have the row; don't fail rollback for that.
            pass

        try:
            self.registry.get_tools()
        except Exception:
            pass

        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _git_commit(self, skill_path: Path) -> bool:
        """Stage and commit *skill_path* to git.  Returns False on failure."""
        try:
            subprocess.run(
                ["git", "add", str(skill_path)],
                check=False,
                capture_output=True,
                timeout=30,
            )
            proc = subprocess.run(
                ["git", "commit", "-m", f"feat: promote skill {skill_path.stem}"],
                check=False,
                capture_output=True,
                timeout=30,
            )
            return proc.returncode == 0
        except Exception:
            return False