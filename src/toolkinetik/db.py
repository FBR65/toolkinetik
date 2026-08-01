"""SQLite metadata store for the skill registry."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class SkillStore:
    """Manages skill metadata in a SQLite database."""

    def __init__(self, db_path: str) -> None:
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    name        TEXT PRIMARY KEY,
                    module      TEXT NOT NULL,
                    function    TEXT NOT NULL,
                    description TEXT,
                    signature   TEXT,
                    version     TEXT NOT NULL DEFAULT '1.0.0',
                    status      TEXT NOT NULL DEFAULT 'active',
                    created_by  TEXT,
                    git_commit  TEXT,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def register_skill(
        self,
        name: str,
        module: str,
        function: str,
        description: str = "",
        signature: str = "",
        version: str = "1.0.0",
        created_by: str = "",
        git_commit: str = "",
    ) -> None:
        """Insert or replace a skill row."""
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO skills
                    (name, module, function, description, signature,
                     version, status, created_by, git_commit,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (name, module, function, description, signature,
                 version, created_by, git_commit, now, now),
            )
            conn.commit()

    def get_skill(self, name: str) -> Optional[Dict[str, Any]]:
        """Return skill metadata dict or None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM skills WHERE name = ?", (name,)
            ).fetchone()
            return dict(row) if row else None

    def list_skills(self) -> List[Dict[str, Any]]:
        """Return all active (non-deleted) skills."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM skills WHERE status = 'active' ORDER BY name"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_version(self, name: str, version: str) -> None:
        """Update the version of a skill."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE skills SET version = ?, updated_at = ? WHERE name = ?",
                (version, self._now(), name),
            )
            conn.commit()

    def delete_skill(self, name: str) -> None:
        """Soft-delete a skill by setting status='deleted'."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE skills SET status = 'deleted', updated_at = ? WHERE name = ?",
                (self._now(), name),
            )
            conn.commit()