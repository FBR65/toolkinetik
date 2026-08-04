"""Tests for SkillStore UPSERT preserving created_at (#13).

SPEC: docs/SPEC-25-improvements.md #13
Tier 2 — re-promotion of a skill must NOT overwrite created_at.
"""

from __future__ import annotations

import time

from toolkinetik.db import SkillStore


def _make_store(tmp_path):
    return SkillStore(str(tmp_path / "test.db"))


def _sample_kwargs():
    return {
        "name": "foo_skill",
        "module": "foo_skill",
        "function": "foo_skill",
        "description": "demo",
        "signature": "def foo(): pass",
        "version": "1.0.0",
        "created_by": "tester",
        "git_commit": "abc",
    }


class TestUpsertPreservesCreatedAt:
    def test_re_promotion_keeps_created_at(self, tmp_path):
        store = _make_store(tmp_path)
        store.register_skill(**_sample_kwargs())
        first = store.get_skill("foo_skill")
        assert first is not None
        original_created = first["created_at"]

        time.sleep(0.01)
        store.register_skill(**_sample_kwargs())
        second = store.get_skill("foo_skill")
        assert second is not None
        assert second["created_at"] == original_created, "created_at must not change on re-promotion"
        assert second["updated_at"] >= first["updated_at"]

    def test_re_promotion_updates_other_fields(self, tmp_path):
        store = _make_store(tmp_path)
        store.register_skill(**_sample_kwargs())
        time.sleep(0.01)
        kw = _sample_kwargs()
        kw["description"] = "updated description"
        kw["version"] = "2.0.0"
        store.register_skill(**kw)
        row = store.get_skill("foo_skill")
        assert row is not None
        assert row["description"] == "updated description"
        assert row["version"] == "2.0.0"

    def test_new_skill_gets_created_at(self, tmp_path):
        store = _make_store(tmp_path)
        store.register_skill(**_sample_kwargs())
        row = store.get_skill("foo_skill")
        assert row is not None
        assert row["created_at"]
        assert row["updated_at"] == row["created_at"]

    def test_update_version_preserves_created_at(self, tmp_path):
        store = _make_store(tmp_path)
        store.register_skill(**_sample_kwargs())
        first = store.get_skill("foo_skill")
        time.sleep(0.01)
        store.update_version("foo_skill", "3.0.0")
        second = store.get_skill("foo_skill")
        assert second["created_at"] == first["created_at"]
        assert second["updated_at"] >= first["updated_at"]
        assert second["version"] == "3.0.0"