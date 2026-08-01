"""Tests for the DynamicToolRegistry."""

from __future__ import annotations

import textwrap
from pathlib import Path

from toolkinetik.registry import DynamicToolRegistry


def _write_skill(path: Path, code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")


def test_registry_loads_skills_from_directory(tmp_path):
    """get_tools discovers and returns public functions from skill files."""
    _write_skill(
        tmp_path / "echo_skill.py",
        """
        def echo(text: str) -> str:
            return text
        """,
    )
    _write_skill(
        tmp_path / "greet_skill.py",
        """
        def greet(name: str) -> str:
            return f"Hello {name}"
        """,
    )

    registry = DynamicToolRegistry(str(tmp_path))
    tools = registry.get_tools()

    names = {t.__name__ for t in tools}
    assert "echo" in names
    assert "greet" in names
    assert "echo" in registry.registered_tools
    assert "greet" in registry.registered_tools


def test_registry_hot_reload(tmp_path):
    """get_tools picks up new files added after initial load (hot reload)."""
    _write_skill(
        tmp_path / "first_skill.py",
        """
        def first() -> str:
            return "first"
        """,
    )

    registry = DynamicToolRegistry(str(tmp_path))
    tools1 = registry.get_tools()
    assert any(t.__name__ == "first" for t in tools1)

    # Add a new skill file after initial load
    _write_skill(
        tmp_path / "second_skill.py",
        """
        def second() -> str:
            return "second"
        """,
    )

    tools2 = registry.get_tools()
    names = {t.__name__ for t in tools2}
    assert "first" in names
    assert "second" in names  # hot-reload picked up the new file


def test_registry_skips_dunder_files(tmp_path):
    """Files starting with __ (dunder) are not loaded as skill modules."""
    _write_skill(
        tmp_path / "__init__.py",
        """
        def should_not_load() -> str:
            return "nope"
        """,
    )
    _write_skill(
        tmp_path / "__helper__.py",
        """
        def also_should_not_load() -> str:
            return "nope"
        """,
    )
    _write_skill(
        tmp_path / "real_skill.py",
        """
        def real_func() -> str:
            return "yes"
        """,
    )

    registry = DynamicToolRegistry(str(tmp_path))
    tools = registry.get_tools()
    names = {t.__name__ for t in tools}

    assert "real_func" in names
    assert "should_not_load" not in names
    assert "also_should_not_load" not in names