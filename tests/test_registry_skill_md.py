"""Tests for DynamicToolRegistry with SKILL.md integration (P0.7).

SPEC: docs/SPEC-production-readiness.md P0.7
Verifies that DynamicToolRegistry discovers both legacy *.py skills AND
new SKILL.md-based skills, while preserving the existing contract
(list[Callable] with __name__, registered_tools dict, hot-reload).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from toolkinetik.registry import DynamicToolRegistry


def _write_skill(path: Path, code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")


def _write_skill_md(path: Path, frontmatter: str, body: str = "# Skill\n\nDoes things.") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")


class TestRegistrySkillMdIntegration:
    def test_discovers_both_py_and_skill_md(self, tmp_path: Path):
        """Registry loads legacy *.py and new SKILL.md skills."""
        _write_skill(tmp_path / "echo.py", "def echo(text): return text")
        _write_skill_md(tmp_path / "productivity" / "docx" / "SKILL.md",
                        'name: docx\ndescription: "Word docs"\nversion: 1.0.0')

        registry = DynamicToolRegistry(str(tmp_path))
        tools = registry.get_tools()
        names = {t.__name__ for t in tools}

        assert "echo" in names  # legacy
        assert "docx" in names  # SKILL.md

    def test_skill_md_tools_are_callable(self, tmp_path: Path):
        """SKILL.md-based tools are callable (SkillTool instances)."""
        _write_skill_md(tmp_path / "test" / "SKILL.md",
                        'name: test_skill\ndescription: "A test"\nversion: 1.0.0')
        registry = DynamicToolRegistry(str(tmp_path))
        tools = registry.get_tools()

        tool = next(t for t in tools if t.__name__ == "test_skill")
        assert callable(tool)
        assert tool.__name__ == "test_skill"
        assert tool.__doc__ == "A test"

    def test_registered_tools_dict_has_both_types(self, tmp_path: Path):
        """registered_tools dict has entries for both *.py and SKILL.md."""
        _write_skill(tmp_path / "math.py", "def add(a, b): return a + b")
        _write_skill_md(tmp_path / "doc" / "SKILL.md",
                        'name: docx\ndescription: "docs"\nversion: 1.0.0')

        registry = DynamicToolRegistry(str(tmp_path))
        registry.get_tools()

        assert "add" in registry.registered_tools
        assert "docx" in registry.registered_tools

    def test_registered_skill_descriptions_populated(self, tmp_path: Path):
        """registered_skill_descriptions has descriptions for SKILL.md skills."""
        _write_skill_md(tmp_path / "doc" / "SKILL.md",
                        'name: docx\ndescription: "Create Word docs"\nversion: 1.0.0')
        registry = DynamicToolRegistry(str(tmp_path))
        registry.get_tools()

        assert "docx" in registry.registered_skill_descriptions
        assert "Create Word docs" in registry.registered_skill_descriptions["docx"]

    def test_hot_reload_picks_up_new_skill_md(self, tmp_path: Path):
        """Adding a new SKILL.md after initial load is picked up on reload."""
        _write_skill_md(tmp_path / "first" / "SKILL.md",
                        'name: first\ndescription: "1"\nversion: 1.0.0')
        registry = DynamicToolRegistry(str(tmp_path))
        tools1 = registry.get_tools()
        assert any(t.__name__ == "first" for t in tools1)

        _write_skill_md(tmp_path / "second" / "SKILL.md",
                        'name: second\ndescription: "2"\nversion: 1.0.0')
        tools2 = registry.get_tools()
        names = {t.__name__ for t in tools2}
        assert "first" in names
        assert "second" in names

    def test_legacy_py_skills_still_work(self, tmp_path: Path):
        """Legacy *.py skills are still loaded and callable (regression)."""
        _write_skill(tmp_path / "weather.py", """
        def get_current_weather(city: str) -> str:
            return f"Weather in {city}"
        """)
        registry = DynamicToolRegistry(str(tmp_path))
        tools = registry.get_tools()
        tool = next(t for t in tools if t.__name__ == "get_current_weather")
        assert tool("Berlin") == "Weather in Berlin"

    def test_skips_dunder_py_files(self, tmp_path: Path):
        """__init__.py is still skipped (regression)."""
        _write_skill(tmp_path / "__init__.py", "def hidden(): return 'nope'")
        _write_skill_md(tmp_path / "real" / "SKILL.md",
                        'name: real\ndescription: "real"\nversion: 1.0.0')
        registry = DynamicToolRegistry(str(tmp_path))
        tools = registry.get_tools()
        names = {t.__name__ for t in tools}
        assert "hidden" not in names
        assert "real" in names


class TestRegistryRealSkills:
    """Integration: registry loads the real skills/ directory."""

    def test_loads_real_skill_collection(self):
        """The real skills/ dir loads both legacy .py and SKILL.md skills."""
        registry = DynamicToolRegistry("skills")
        tools = registry.get_tools()
        names = {t.__name__ for t in tools}

        # Legacy
        assert "calculate_fibonacci" in names or "get_current_weather" in names
        # SKILL.md
        assert "docx" in names
        assert "test-driven-development" in names
        assert "github-code-review" in names

    def test_real_skill_descriptions_populated(self):
        """Real skills have descriptions in registered_skill_descriptions."""
        registry = DynamicToolRegistry("skills")
        registry.get_tools()
        assert "docx" in registry.registered_skill_descriptions
        desc = registry.registered_skill_descriptions["docx"]
        assert "docx" in desc.lower() or "word" in desc.lower()