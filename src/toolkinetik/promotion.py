"""Skill promotion & hot-reload pipeline with git-based rollback.

Task 3.3: SkillPromoter writes a generated skill to the skills directory,
triggers the DynamicToolRegistry hot-reload, registers metadata in the
SQLite SkillStore, and commits the change to git.  Rollback removes the
file, marks the DB row as deleted, and re-triggers hot-reload.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from toolkinetik.config import get_settings
from toolkinetik.db import SkillStore
from toolkinetik.registry import DynamicToolRegistry

logger = logging.getLogger(__name__)

# Process-global lock for git operations (prevents index.lock races).
_git_lock = threading.Lock()


def safe_skill_path(skills_dir: str, skill_name: str) -> Path | None:
    """Resolve ``<skills_dir>/<skill_name>.py`` and guard against path traversal.

    Returns the resolved path if it stays inside *skills_dir*, otherwise ``None``.
    Handles ``..`` segments and absolute paths.
    """
    base = Path(skills_dir).resolve()
    candidate = (base / f"{skill_name}.py").resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


@dataclass
class PromotionResult:
    """Outcome of a promotion attempt."""

    success: bool
    skill_path: str = ""
    error: str = ""
    git_committed: bool = False


class SkillPromoter:
    """Promote generated skills to the live registry and commit to git."""

    _git_lock = _git_lock  # class-level reference for test visibility

    def __init__(
        self,
        skills_dir: str | None = None,
        registry: DynamicToolRegistry | None = None,
        db: SkillStore | None = None,
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
        metadata: dict | None = None,
    ) -> PromotionResult:
        """Write *code* to ``<skills_dir>/<skill_name>.py`` and register it."""
        skill_path = safe_skill_path(self.skills_dir, skill_name)
        if skill_path is None:
            return PromotionResult(
                success=False,
                error=f"path traversal detected in skill name: {skill_name!r}",
            )
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
        skill_path = safe_skill_path(self.skills_dir, skill_name)
        if skill_path is None:
            return False
        try:
            if skill_path.exists():
                skill_path.unlink()
        except OSError:
            return False

        try:
            self.db.delete_skill(skill_name)
        except Exception:
            # DB may not have the row; don't fail rollback for that.
            logger.exception("rollback: db.delete_skill failed for %r", skill_name)

        try:
            self.registry.get_tools()
        except Exception:
            pass

        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _git_commit(self, skill_path: Path) -> bool:
        """Stage and commit *skill_path* to git.  Returns False on failure.

        Uses a process-global lock to prevent index.lock races between
        parallel promotions. Retries up to 3 times on index.lock errors.
        """
        max_retries = 3
        backoff_s = 0.1
        with self._git_lock:
            for attempt in range(max_retries):
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
                    if proc.returncode == 0:
                        return True
                    stderr = proc.stderr or ""
                    if "index.lock" in stderr and attempt < max_retries - 1:
                        logger.warning("git index.lock conflict, retrying (attempt %d)", attempt + 1)
                        time.sleep(backoff_s)
                        continue
                    return False
                except Exception:
                    return False
            return False