"""Dynamic tool registry with hot-reload support."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from collections.abc import Callable
from glob import glob
from pathlib import Path

# Prefix for skill modules to avoid collisions in sys.modules.
_MODULE_PREFIX = "toolkinetik_skills_"


class DynamicToolRegistry:
    """Discovers, imports, and tracks callable tools from a skills directory.

    Skills are plain ``.py`` files.  Any top-level function whose name does
    *not* start with an underscore is exposed as a tool.  Modules whose
    filename starts with ``__`` (dunder files like ``__init__.py``) are
    skipped entirely.  Calling :meth:`get_tools` again reloads modules so
    that new or changed skills are picked up without a restart (hot reload).

    Uses ``importlib.util.spec_from_file_location`` for explicit file-based
    loading so that multiple registries with different directories work
    correctly and modules are always re-read from disk.
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

    def get_tools(self) -> list[Callable]:
        """Scan ``skills_dir`` for ``*.py`` files and collect public callables.

        Returns a fresh list every call (supports hot reload).
        """
        importlib.invalidate_caches()
        self.registered_tools = {}
        pattern = str(Path(self.skills_dir) / "*.py")
        skill_files = sorted(glob(pattern))

        # Avoid stale .pyc bytecode when hot-reloading source edits.
        prev_dont_write = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            for filepath in skill_files:
                stem = Path(filepath).stem

                # Skip dunder files (__init__, __helper__, etc.)
                if stem.startswith("__"):
                    continue

                module_name = _MODULE_PREFIX + stem

                # Always (re)load from disk for hot-reload support.
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                # Register in sys.modules so importlib.reload works and
                # intra-package references resolve.
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Collect public callables (functions defined in this module).
                for attr_name, obj in inspect.getmembers(module, inspect.isfunction):
                    # Skip private/dunder functions
                    if attr_name.startswith("_"):
                        continue
                    # Only functions actually defined in this module (not imports)
                    if obj.__module__ != module_name:
                        continue
                    self.registered_tools[attr_name] = obj
        finally:
            sys.dont_write_bytecode = prev_dont_write

        return list(self.registered_tools.values())