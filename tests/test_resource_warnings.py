"""Tests for ResourceWarnings fix (P3.1).

SPEC: docs/SPEC-production-readiness.md P3.1
SQLite connections must be closed properly; no ResourceWarnings from db.py.
"""

from __future__ import annotations

import gc
import warnings
from pathlib import Path

from toolkinetik.db import SkillStore


class TestNoResourceWarnings:
    def test_skillstore_no_unclosed_connections(self, tmp_path: Path):
        """SkillStore operations must not leave unclosed sqlite connections."""
        store = SkillStore(str(tmp_path / "test.db"))
        # Perform several operations
        store.register_skill("skill1", "mod1", "func1")
        store.register_skill("skill2", "mod2", "func2")
        store.list_skills()
        store.get_skill("skill1")
        store.update_version("skill1", "2.0.0")
        store.delete_skill("skill1")

        # Force garbage collection and check for ResourceWarnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            gc.collect()
            sqlite_warnings = [w for w in caught if issubclass(w.category, ResourceWarning) and "sqlite" in str(w.message).lower()]
            assert len(sqlite_warnings) == 0, f"unclosed sqlite connections: {sqlite_warnings}"

    def test_multiple_skillstore_instances_no_leak(self, tmp_path: Path):
        """Multiple SkillStore instances don't leak connections."""
        for i in range(10):
            store = SkillStore(str(tmp_path / f"db_{i}.db"))
            store.register_skill(f"skill_{i}", "mod", "func")
            store.list_skills()

        gc.collect()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            gc.collect()
            sqlite_warnings = [w for w in caught if issubclass(w.category, ResourceWarning) and "sqlite" in str(w.message).lower()]
            assert len(sqlite_warnings) == 0