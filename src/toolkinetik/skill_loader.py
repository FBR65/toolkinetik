"""SkillLoader — discovers SKILL.md-based skills in the skills directory.

P0.7: The new skill collection uses the Hermes/Anthropic skill format:
each skill is a directory containing a SKILL.md file with YAML frontmatter
(name, description, version) plus optional scripts/, references/, templates/.

This module parses the frontmatter and exposes SkillInfo objects so the
DynamicToolRegistry can register them alongside the legacy *.py skills.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    """Metadata for a single SKILL.md-based skill."""

    name: str
    description: str = ""
    version: str = "1.0.0"
    skill_dir: Path = field(default_factory=Path)
    has_scripts: bool = False
    scripts_dir: Path | None = None
    body: str = ""


def parse_frontmatter(text: str) -> SkillInfo | None:
    """Parse a SKILL.md file's content and extract skill metadata.

    Returns None if the text has no valid frontmatter or is missing the
    required ``name`` field.
    """
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return None

    # Find the closing --- delimiter.
    end = stripped.find("\n---", 3)
    if end == -1:
        return None

    frontmatter_text = stripped[3:end].strip()
    body = stripped[end + 4:].lstrip()  # skip past closing ---\n

    if not frontmatter_text:
        return None

    try:
        data = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return None

    if not isinstance(data, dict):
        return None

    name = data.get("name")
    if not name or not isinstance(name, str):
        return None

    return SkillInfo(
        name=name,
        description=str(data.get("description", "")),
        version=str(data.get("version", "1.0.0")),
        body=body,
    )


class SkillLoader:
    """Discovers SKILL.md-based skills in a directory tree."""

    # Directories that are not skill collections.
    _SKIP_DIRS = {"index-cache", "__pycache__", ".git", "node_modules"}

    def __init__(self, skills_dir: str) -> None:
        self.skills_dir = Path(skills_dir).resolve()

    def discover_skills(self) -> list[SkillInfo]:
        """Recursively find all SKILL.md files and parse their frontmatter.

        Returns a list of SkillInfo objects, one per valid SKILL.md found.
        """
        if not self.skills_dir.exists():
            return []

        skills: list[SkillInfo] = []
        for skill_md_path in sorted(self.skills_dir.rglob("SKILL.md")):
            # Skip paths that go through a skipped directory.
            rel_parts = skill_md_path.relative_to(self.skills_dir).parts
            if any(part in self._SKIP_DIRS for part in rel_parts[:-1]):
                continue

            try:
                content = skill_md_path.read_text(encoding="utf-8")
            except OSError:
                logger.warning("could not read %s", skill_md_path)
                continue

            info = parse_frontmatter(content)
            if info is None:
                logger.debug("no valid frontmatter in %s", skill_md_path)
                continue

            skill_dir = skill_md_path.parent.resolve()
            info.skill_dir = skill_dir
            scripts_dir = skill_dir / "scripts"
            if scripts_dir.is_dir():
                info.has_scripts = True
                info.scripts_dir = scripts_dir

            skills.append(info)

        return skills