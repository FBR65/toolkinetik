"""SQLite metadata store for the skill registry."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SkillStore:
    """Manages skill metadata in a SQLite database."""

    def __init__(self, db_path: str) -> None:
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self):
        """Open a connection that is closed on exit (fixes ResourceWarnings).

        sqlite3.Connection's own __enter__/__exit__ only manages the
        transaction (commit/rollback), it does NOT close the connection.
        This contextmanager ensures the connection is closed.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            # Enable WAL mode for concurrent write safety (P1.4).
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")  # 5s timeout for locked DB
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
            # Schema version tracking (P2.4)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            # Initialize with version 1 if empty
            count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
            if count == 0:
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (1, ?)",
                    (self._now(),),
                )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

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
        """Insert a new skill, or update an existing one while preserving created_at."""
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO skills
                    (name, module, function, description, signature,
                     version, status, created_by, git_commit,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    module      = excluded.module,
                    function    = excluded.function,
                    description = excluded.description,
                    signature   = excluded.signature,
                    version     = excluded.version,
                    status      = excluded.status,
                    created_by  = excluded.created_by,
                    git_commit  = excluded.git_commit,
                    updated_at  = excluded.updated_at
                """,
                (name, module, function, description, signature,
                 version, created_by, git_commit, now, now),
            )

    def get_skill(self, name: str) -> dict[str, Any] | None:
        """Return skill metadata dict or None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM skills WHERE name = ?", (name,)
            ).fetchone()
            return dict(row) if row else None

    def list_skills(self) -> list[dict[str, Any]]:
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

    def delete_skill(self, name: str) -> None:
        """Soft-delete a skill by setting status='deleted'."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE skills SET status = 'deleted', updated_at = ? WHERE name = ?",
                (self._now(), name),
            )