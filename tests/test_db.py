"""Tests for the SQLite SkillStore metadata store."""

from __future__ import annotations

import time

from toolkinetik.db import SkillStore


def _make_store(tmp_path):
    db_path = tmp_path / "test.db"
    return SkillStore(str(db_path))


def _sample_skill_kwargs():
    return dict(
        name="weather_skill",
        module="skills.weather_skill",
        function="get_current_weather",
        description="Ruft das aktuelle Wetter ab.",
        signature="get_current_weather(location: str) -> str",
        version="1.0.0",
        created_by="system",
        git_commit="abc1234",
    )


def test_register_skill(tmp_path):
    """register_skill inserts a row that can be retrieved."""
    store = _make_store(tmp_path)
    kw = _sample_skill_kwargs()
    store.register_skill(**kw)
    row = store.get_skill(kw["name"])
    assert row is not None
    assert row["name"] == kw["name"]
    assert row["module"] == kw["module"]
    assert row["function"] == kw["function"]
    assert row["description"] == kw["description"]
    assert row["signature"] == kw["signature"]
    assert row["version"] == kw["version"]
    assert row["created_by"] == kw["created_by"]
    assert row["git_commit"] == kw["git_commit"]
    assert row["status"] == "active"


def test_get_skill_metadata(tmp_path):
    """get_skill returns None for unknown skill and metadata for known."""
    store = _make_store(tmp_path)
    assert store.get_skill("nonexistent") is None

    kw = _sample_skill_kwargs()
    store.register_skill(**kw)
    meta = store.get_skill(kw["name"])
    assert meta is not None
    assert meta["name"] == kw["name"]
    assert "created_at" in meta
    assert "updated_at" in meta


def test_update_skill_version(tmp_path):
    """update_version changes the version and bumps updated_at."""
    store = _make_store(tmp_path)
    kw = _sample_skill_kwargs()
    store.register_skill(**kw)
    original = store.get_skill(kw["name"])
    assert original["version"] == "1.0.0"

    time.sleep(0.01)  # ensure timestamp differs
    store.update_version(kw["name"], "2.0.0")
    updated = store.get_skill(kw["name"])
    assert updated["version"] == "2.0.0"
    assert updated["updated_at"] >= original["updated_at"]


def test_delete_skill(tmp_path):
    """delete_skill soft-deletes (status='deleted') and removes from list_skills."""
    store = _make_store(tmp_path)
    kw = _sample_skill_kwargs()
    store.register_skill(**kw)
    assert len(store.list_skills()) == 1

    store.delete_skill(kw["name"])
    # Should not appear in active list
    assert len(store.list_skills()) == 0
    # But still retrievable via get_skill (metadata still present)
    row = store.get_skill(kw["name"])
    assert row is not None
    assert row["status"] == "deleted"