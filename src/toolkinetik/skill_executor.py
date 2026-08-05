"""SkillExecutor — executes SKILL.md-based skills by delegating to a Coding-Agent.

P0.7: SKILL.md skills are procedural knowledge for coding agents (Claude Code,
Codex, OpenCode). The SkillExecutor takes a SkillInfo, builds a prompt that
includes the SKILL.md body as context, and delegates execution to a CodingAgent.

SkillTool wraps a SkillInfo + SkillExecutor into a callable with __name__ and
__doc__, so it can be registered in DynamicToolRegistry alongside legacy
Python-function skills.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from toolkinetik.coding_agent import SkillSpec
from toolkinetik.skill_loader import SkillInfo

logger = logging.getLogger(__name__)


class SkillExecutor:
    """Executes SKILL.md-based skills via a coding agent."""

    def __init__(self, coding_agent: Any = None) -> None:
        self._coding_agent = coding_agent

    def execute(self, info: SkillInfo, *args: Any, **kwargs: Any) -> str:
        """Execute a skill by delegating to the coding agent.

        Returns a string result. If no coding agent is available, returns
        a graceful fallback message describing the skill.
        """
        if self._coding_agent is None:
            logger.info("no coding agent available for skill %r; returning fallback", info.name)
            return f"[skill:{info.name}] {info.description}"

        prompt = self._build_prompt(info, args, kwargs)
        return self._delegate_to_agent(info, prompt)

    def _build_prompt(self, info: SkillInfo, args: tuple, kwargs: dict) -> str:
        """Build the prompt sent to the coding agent."""
        parts = [
            f"# Skill: {info.name}",
            f"Description: {info.description}",
            f"Version: {info.version}",
            "",
            "## Skill Instructions (SKILL.md)",
            info.body or "(no instructions)",
            "",
        ]
        if info.has_scripts and info.scripts_dir is not None:
            parts.append("## Helper Scripts")
            parts.append(f"Available in: `{info.scripts_dir}`")
            scripts = self._list_scripts(info.scripts_dir)
            if scripts:
                parts.append("Scripts:")
                for s in scripts:
                    parts.append(f"  - {s}")
            parts.append("")

        if args or kwargs:
            parts.append("## Call Arguments")
            if args:
                parts.append(f"  positional: {args}")
            if kwargs:
                parts.append(f"  keyword: {kwargs}")
            parts.append("")

        parts.append("Execute this skill according to its instructions. Use the helper scripts if available.")
        return "\n".join(parts)

    def _delegate_to_agent(self, info: SkillInfo, prompt: str) -> str:
        """Delegate the prompt to the coding agent and return its output."""
        try:
            result = self._coding_agent.create_skill(
                spec=SkillSpec(
                    name=info.name,
                    description=info.description,
                    signature=f"def {info.name}(*args, **kwargs):",
                    test_cases=[],
                ),
            )
            return result.code if hasattr(result, "code") else str(result)
        except Exception:
            logger.exception("coding agent delegation failed for skill %r", info.name)
            return f"[skill:{info.name}] execution failed — see logs"

    def get_scripts(self, info: SkillInfo) -> Path | None:
        """Return the scripts directory if the skill has helper scripts."""
        if info.has_scripts and info.scripts_dir is not None:
            return info.scripts_dir
        return None

    @staticmethod
    def _list_scripts(scripts_dir: Path) -> list[str]:
        """List Python script filenames in a scripts directory."""
        if not scripts_dir.exists():
            return []
        return sorted(p.name for p in scripts_dir.glob("*.py") if not p.name.startswith("__"))


class SkillTool:
    """Callable wrapper around a SKILL.md-based skill.

    Implements the DynamicToolRegistry contract: callable with __name__
    and __doc__, so it can be registered alongside legacy Python functions.
    """

    def __init__(self, info: SkillInfo, executor: SkillExecutor | None = None) -> None:
        self._info = info
        self._executor = executor or SkillExecutor()
        self.__name__ = info.name
        self.__doc__ = info.description
        self._skill_dir = info.skill_dir

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        """Execute the skill by delegating to the SkillExecutor."""
        return self._executor.execute(self._info, *args, **kwargs)