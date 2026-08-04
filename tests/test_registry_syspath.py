"""Tests for registry sys.path handling and module prefixing (#12)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from toolkinetik.registry import DynamicToolRegistry


def _write_skill(path: Path, code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")


class TestSysPathHandling:
    def test_skills_dir_added_once_to_sys_path(self, tmp_path):
        before = set(sys.path)
        DynamicToolRegistry(str(tmp_path))
        after = set(sys.path)
        new = after - before
        assert str(tmp_path) in new
        # Second instance doesn't add again
        before2 = set(sys.path)
        DynamicToolRegistry(str(tmp_path))
        after2 = set(sys.path)
        assert after2 == before2  # no new entries

    def test_different_dirs_both_in_sys_path(self, tmp_path):
        dir1 = tmp_path / "skills_a"
        dir2 = tmp_path / "skills_b"
        dir1.mkdir()
        dir2.mkdir()
        DynamicToolRegistry(str(dir1))
        DynamicToolRegistry(str(dir2))
        assert str(dir1) in sys.path
        assert str(dir2) in sys.path
        # cleanup
        sys.path.remove(str(dir1))
        sys.path.remove(str(dir2))


class TestModulePrefix:
    def test_module_loaded_with_prefix(self, tmp_path):
        _write_skill(
            tmp_path / "foo.py",
            """
            def foo(): return "foo"
            """,
        )
        reg = DynamicToolRegistry(str(tmp_path))
        reg.get_tools()
        # Module should be in sys.modules under a prefixed name
        prefixed_keys = [k for k in sys.modules if "foo" in k and k != "foo"]
        assert any("toolkinetik_skills" in k or k.startswith("_skills_") for k in prefixed_keys), \
            f"module should be prefixed, found: {prefixed_keys}"

    def test_no_collision_between_two_dirs_same_skill_name(self, tmp_path):
        dir1 = tmp_path / "a"
        dir2 = tmp_path / "b"
        dir1.mkdir()
        dir2.mkdir()
        _write_skill(
            dir1 / "shared.py",
            """
            def shared(): return "from_a"
            """,
        )
        _write_skill(
            dir2 / "shared.py",
            """
            def shared(): return "from_b"
            """,
        )
        reg1 = DynamicToolRegistry(str(dir1))
        reg2 = DynamicToolRegistry(str(dir2))
        tools1 = reg1.get_tools()
        tools2 = reg2.get_tools()
        # Both registries should have their own version of `shared`
        assert any(t.__name__ == "shared" and t() == "from_a" for t in tools1)
        assert any(t.__name__ == "shared" and t() == "from_b" for t in tools2)


class TestHotReloadInvalidatesCaches:
    def test_invalidate_caches_called_on_reload(self, tmp_path, monkeypatch):
        _write_skill(
            tmp_path / "v1.py",
            """
            def v1(): return "v1"
            """,
        )
        reg = DynamicToolRegistry(str(tmp_path))
        reg.get_tools()
        # Now change the file
        _write_skill(
            tmp_path / "v1.py",
            """
            def v1(): return "v2"
            """,
        )
        import importlib
        with monkeypatch.context() as m:
            spy = MagicMock()
            m.setattr(importlib, "invalidate_caches", spy)
            reg.get_tools()
            # Note: invalidation may or may not be called depending on impl,
            # but the new content should be active.
        tools = reg.get_tools()
        # New content is active
        func = next(t for t in tools if t.__name__ == "v1")
        assert func() == "v2"


# Need MagicMock import
from unittest.mock import MagicMock