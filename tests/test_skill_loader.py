"""Tests for SkillLoader — SKILL.md discovery and frontmatter parsing (P0.7).

SPEC: docs/SPEC-production-readiness.md P0.7
Tier 3 — the new skill collection (47 SKILL.md files) must be discoverable.
"""

from __future__ import annotations

from pathlib import Path

from toolkinetik.skill_loader import SkillLoader, parse_frontmatter


def _write_skill_md(path: Path, frontmatter: str, body: str = "# Skill\n\nDoes things.") -> None:
    """Write a SKILL.md file with YAML frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"---\n{frontmatter}\n---\n\n{body}\n"
    path.write_text(content, encoding="utf-8")


class TestParseFrontmatter:
    def test_parse_basic_frontmatter(self):
        text = "---\nname: docx\ndescription: \"Create Word docs\"\nversion: 1.0.0\n---\n\nbody"
        info = parse_frontmatter(text)
        assert info is not None
        assert info.name == "docx"
        assert info.description == "Create Word docs"
        assert info.version == "1.0.0"

    def test_parse_frontmatter_with_metadata(self):
        text = "---\nname: p5js\ndescription: \"p5.js art\"\nversion: 1.1.0\nmetadata:\n  hermes:\n    tags: [art]\n---\n\nbody"
        info = parse_frontmatter(text)
        assert info is not None
        assert info.name == "p5js"
        assert info.version == "1.1.0"

    def test_parse_no_frontmatter_returns_none(self):
        info = parse_frontmatter("just some markdown, no frontmatter")
        assert info is None

    def test_parse_empty_frontmatter_returns_none(self):
        info = parse_frontmatter("---\n---\n\nbody")
        assert info is None

    def test_parse_missing_name_returns_none(self):
        """A SKILL.md without a name field is invalid."""
        info = parse_frontmatter("---\ndescription: \"no name\"\n---\nbody")
        assert info is None


class TestSkillLoaderDiscovery:
    def test_discovers_skill_md_files(self, tmp_path: Path):
        """SkillLoader finds SKILL.md files in subdirectories."""
        _write_skill_md(tmp_path / "creative" / "p5js" / "SKILL.md", "name: p5js\ndescription: \"p5.js\"\nversion: 1.0.0")
        _write_skill_md(tmp_path / "productivity" / "docx" / "SKILL.md", "name: docx\ndescription: \"Word docs\"\nversion: 1.0.0")

        loader = SkillLoader(str(tmp_path))
        skills = loader.discover_skills()

        names = {s.name for s in skills}
        assert "p5js" in names
        assert "docx" in names
        assert len(skills) == 2

    def test_discovers_nested_skills(self, tmp_path: Path):
        """Skills in deeply nested directories are found."""
        _write_skill_md(tmp_path / "a" / "b" / "c" / "SKILL.md", "name: deep\nversion: 1.0.0")
        loader = SkillLoader(str(tmp_path))
        skills = loader.discover_skills()
        assert len(skills) == 1
        assert skills[0].name == "deep"

    def test_skips_index_cache_directory(self, tmp_path: Path):
        """index-cache directory should not be scanned for SKILL.md."""
        _write_skill_md(tmp_path / "index-cache" / "SKILL.md", "name: cache\nversion: 1.0.0")
        _write_skill_md(tmp_path / "real" / "SKILL.md", "name: real\nversion: 1.0.0")
        loader = SkillLoader(str(tmp_path))
        skills = loader.discover_skills()
        names = {s.name for s in skills}
        assert "real" in names
        assert "cache" not in names

    def test_extracts_skill_path(self, tmp_path: Path):
        """SkillInfo.skill_dir points to the directory containing SKILL.md."""
        skill_dir = tmp_path / "productivity" / "docx"
        _write_skill_md(skill_dir / "SKILL.md", "name: docx\ndescription: \"Word\"\nversion: 1.0.0")
        loader = SkillLoader(str(tmp_path))
        skills = loader.discover_skills()
        assert len(skills) == 1
        assert skills[0].skill_dir == skill_dir.resolve()

    def test_has_helper_scripts_flag(self, tmp_path: Path):
        """SkillInfo.has_scripts is True when scripts/ directory exists."""
        skill_dir = tmp_path / "productivity" / "docx"
        _write_skill_md(skill_dir / "SKILL.md", "name: docx\ndescription: \"Word\"\nversion: 1.0.0")
        (skill_dir / "scripts").mkdir(parents=True)
        (skill_dir / "scripts" / "helper.py").write_text("print('hi')")

        loader = SkillLoader(str(tmp_path))
        skills = loader.discover_skills()
        assert skills[0].has_scripts is True

    def test_has_helper_scripts_false_when_no_scripts(self, tmp_path: Path):
        """SkillInfo.has_scripts is False when no scripts/ directory."""
        _write_skill_md(tmp_path / "simple" / "SKILL.md", "name: simple\ndescription: \"simple\"\nversion: 1.0.0")
        loader = SkillLoader(str(tmp_path))
        skills = loader.discover_skills()
        assert skills[0].has_scripts is False

    def test_description_with_quotes(self, tmp_path: Path):
        """Descriptions with quotes are parsed correctly."""
        _write_skill_md(tmp_path / "test" / "SKILL.md", 'name: test\ndescription: "Create, read, edit Word .docx documents"\nversion: 1.0.0')
        loader = SkillLoader(str(tmp_path))
        skills = loader.discover_skills()
        assert skills[0].description == "Create, read, edit Word .docx documents"

    def test_empty_skills_dir_returns_empty(self, tmp_path: Path):
        """No SKILL.md files → empty list."""
        (tmp_path / "empty").mkdir()
        loader = SkillLoader(str(tmp_path))
        skills = loader.discover_skills()
        assert skills == []


class TestSkillLoaderRealSkills:
    """Integration: discover skills in the real skills/ directory."""

    def test_discovers_real_skill_collection(self):
        """The real skills/ directory has 47 SKILL.md files across 7 categories."""
        loader = SkillLoader("skills")
        skills = loader.discover_skills()
        names = {s.name for s in skills}
        # Spot-check a few known skills
        assert "docx" in names
        assert "test-driven-development" in names
        assert "github-code-review" in names
        assert "p5js" in names
        assert "himalaya" in names
        # Must find at least 40 (allowing for format variations)
        assert len(skills) >= 40, f"expected >=40 skills, found {len(skills)}: {sorted(names)}"

    def test_real_skills_have_descriptions(self):
        """Every discovered real skill has a non-empty description."""
        loader = SkillLoader("skills")
        skills = loader.discover_skills()
        for skill in skills:
            assert skill.description, f"skill {skill.name!r} has empty description"

    def test_real_docx_has_scripts(self):
        """The real docx skill has a scripts/ directory."""
        loader = SkillLoader("skills")
        skills = loader.discover_skills()
        docx = next(s for s in skills if s.name == "docx")
        assert docx.has_scripts is True