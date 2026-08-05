"""Dynamic tool registry with hot-reload support."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from collections.abc import Callable
from glob import glob
from pathlib import Path

from toolkinetik.skill_executor import SkillExecutor, SkillTool
from toolkinetik.skill_loader import SkillLoader

# Prefix for skill modules to avoid collisions in sys.modules.
_MODULE_PREFIX = "toolkinetik_skills_"


class DynamicToolRegistry:
    """Discovers, imports, and tracks callable tools from a skills directory.

    Skills come in two formats:
    1. **Legacy *.py** — top-level Python files with public functions.
    2. **SKILL.md** — directories containing a SKILL.md file with YAML
       frontmatter (name, description, version). These are wrapped in
       SkillTool instances that delegate execution to a SkillExecutor.

    Any top-level function (legacy) or SkillTool whose name does not start
    with an underscore is exposed as a tool.  Calling :meth:`get_tools` again
    reloads everything so new or changed skills are picked up without a
    restart (hot reload).
    """

    def __init__(self, skills_dir: str) -> None:
        self.skills_dir = str(skills_dir)
        Path(self.skills_dir).mkdir(parents=True, exist_ok=True)

        # Ensure the skills directory is importable (for intra-skill imports).
        if self.skills_dir not in sys.path:
            sys.path.insert(0, self.skills_dir)

        # Internal cache of loaded modules keyed by module name.
        self._loaded_modules: dict[str, object] = {}
        self.registered_tools: dict[str, Callable] = {}
        self.registered_skill_descriptions: dict[str, str] = {}
        self._skill_loader = SkillLoader(self.skills_dir)

    def get_tools(self) -> list[Callable]:
        """Scan ``skills_dir`` for *.py files and SKILL.md files, collect tools.

        Returns a fresh list every call (supports hot reload).
        """
        importlib.invalidate_caches()
        self.registered_tools = {}
        self.registered_skill_descriptions = {}

        # 1. Legacy: top-level *.py → Python functions.
        self._load_python_skills()

        # 2. New: SKILL.md → SkillTool wrappers.
        self._load_skill_md_skills()

        return list(self.registered_tools.values())

    def _load_python_skills(self) -> None:
        """Load legacy top-level *.py files as Python functions."""
        pattern = str(Path(self.skills_dir) / "*.py")
        skill_files = sorted(glob(pattern))

        prev_dont_write = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            for filepath in skill_files:
                stem = Path(filepath).stem

                if stem.startswith("__"):
                    continue

                module_name = _MODULE_PREFIX + stem

                spec = importlib.util.spec_from_file_location(module_name, filepath)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                for attr_name, obj in inspect.getmembers(module, inspect.isfunction):
                    if attr_name.startswith("_"):
                        continue
                    if obj.__module__ != module_name:
                        continue
                    self.registered_tools[attr_name] = obj
                    if obj.__doc__:
                        self.registered_skill_descriptions[attr_name] = obj.__doc__
        finally:
            sys.dont_write_bytecode = prev_dont_write

    def _load_skill_md_skills(self) -> None:
        """Load SKILL.md-based skills as SkillTool wrappers."""
        skills = self._skill_loader.discover_skills()
        executor = SkillExecutor()
        for info in skills:
            if info.name in self.registered_tools:
                # Legacy *.py skill with same name wins (don't overwrite).
                continue
            tool = SkillTool(info, executor=executor)
            self.registered_tools[info.name] = tool
            self.registered_skill_descriptions[info.name] = info.description