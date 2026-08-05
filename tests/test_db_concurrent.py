"""Tests for SQLite WAL mode and concurrent writes (P1.4).

SPEC: docs/SPEC-production-readiness.md P1.4
SQLite must use WAL mode for concurrent write safety, with retry on
"database is locked" errors.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from toolkinetik.db import SkillStore


@pytest.fixture
def store(tmp_path: Path) -> SkillStore:
    db_path = str(tmp_path / "test.db")
    return SkillStore(db_path)


class TestWalMode:
    def test_wal_mode_enabled(self, store: SkillStore):
        """SkillStore initializes with WAL journal mode."""
        conn = sqlite3.connect(store.db_path)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        assert result[0].lower() == "wal"


class TestConcurrentWrites:
    def test_parallel_registrations_no_lock_error(self, store: SkillStore):
        """10 threads registering skills simultaneously — no OperationalError."""
        errors: list[Exception] = []

        def register_one(i: int):
            try:
                store.register_skill(
                    name=f"skill_{i}",
                    module=f"skill_{i}",
                    function=f"skill_{i}",
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=register_one, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"concurrent writes produced errors: {errors}"

        # Verify all 10 skills are in the DB
        skills = store.list_skills()
        assert len(skills) == 10

    def test_all_skills_persisted_after_parallel_writes(self, store: SkillStore):
        """After parallel writes, all skills are retrievable."""
        threads = []
        for i in range(5):
            t = threading.Thread(
                target=store.register_skill,
                args=(f"parallel_{i}", f"parallel_{i}", f"parallel_{i}"),
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=10)

        names = {s["name"] for s in store.list_skills()}
        assert {"parallel_0", "parallel_1", "parallel_2", "parallel_3", "parallel_4"}.issubset(names)