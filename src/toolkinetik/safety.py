"""Safety checker, skill versioning, and rollback support.

Task 5.2: SafetyChecker extends the static security check from tdd_loop.py
into a reusable component that AST-parses code for forbidden calls and
forbidden imports. SkillVersionManager tracks per-skill versions and
git history for rollback support.
"""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# SafetyReport dataclass
# ---------------------------------------------------------------------------


@dataclass
class SafetyReport:
    """Outcome of a safety check on a piece of code."""

    passed: bool
    issues: list = field(default_factory=list)
    forbidden_calls: list = field(default_factory=list)
    forbidden_imports: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# SafetyChecker
# ---------------------------------------------------------------------------


class SafetyChecker:
    """AST-based static analysis for forbidden calls and imports."""

    FORBIDDEN_CALLS = {
        "os.system",
        "os.popen",
        "subprocess.call",
        "subprocess.run",
        "subprocess.Popen",
        "eval",
        "exec",
        "__import__",
        "compile",
    }

    # Map of forbidden simple/builtin call names (no module prefix).
    _FORBIDDEN_BUILTIN_CALLS = {"eval", "exec", "__import__", "compile"}

    # Map of "module.attr" patterns for forbidden attribute calls.
    _FORBIDDEN_ATTR_CALLS = {
        "os.system",
        "os.popen",
        "subprocess.call",
        "subprocess.run",
        "subprocess.Popen",
    }

    # Explicitly allowed standard-library modules. Any import whose top-level
    # module is NOT in this set is flagged. Relative imports (`.module`) and
    # imports of sibling skill modules in the skills directory are always
    # allowed. This is a whitelist: unknown modules are rejected by default.
    ALLOWED_STDLIB = {
        "math",
        "json",
        "re",
        "datetime",
        "collections",
        "itertools",
        "functools",
        "random",
        "statistics",
        "typing",
        "enum",
        "decimal",
        "fractions",
    }

    FORBIDDEN_IMPORTS = {"os", "subprocess", "shutil", "ctypes"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_code(self, code: str) -> SafetyReport:
        """AST-parse *code* and check for forbidden calls and imports.

        Returns a SafetyReport.  If the code has a syntax error, the report
        has ``passed=False`` with an issue describing the error.
        """
        issues: list[str] = []
        forbidden_calls: list[str] = []
        forbidden_imports: list[str] = []

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return SafetyReport(
                passed=False,
                issues=[f"syntax error: {exc}"],
                forbidden_calls=[],
                forbidden_imports=[],
            )

        for node in ast.walk(tree):
            # -- Check forbidden imports --------------------------------
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".")[0]
                    if root_name in self.FORBIDDEN_IMPORTS:
                        forbidden_imports.append(f"import {alias.name}")
                        issues.append(f"forbidden import: {alias.name}")
                    elif root_name not in self.ALLOWED_STDLIB:
                        forbidden_imports.append(f"import {alias.name}")
                        issues.append(f"disallowed import: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                # Relative imports (node.level > 0, e.g. `from .module import`)
                # reference sibling skill modules and are always allowed.
                if node.level > 0:
                    continue
                module = node.module or ""
                root_name = module.split(".")[0]
                if root_name in self.FORBIDDEN_IMPORTS:
                    # Report the full from-import module.
                    imported = node.module
                    forbidden_imports.append(f"from {imported} import ...")
                    issues.append(f"forbidden import: {imported}")
                elif root_name not in self.ALLOWED_STDLIB:
                    forbidden_imports.append(f"from {module} import ...")
                    issues.append(f"disallowed import: {module}")

            # -- Check forbidden calls ----------------------------------
            if isinstance(node, ast.Call):
                func = node.func

                # Direct builtin call: eval(...), exec(...), __import__(...), compile(...)
                if isinstance(func, ast.Name) and func.id in self._FORBIDDEN_BUILTIN_CALLS:
                    call_str = func.id
                    forbidden_calls.append(call_str)
                    issues.append(f"forbidden call: {call_str}()")

                # Attribute call: os.system(...), subprocess.run(...), etc.
                elif isinstance(func, ast.Attribute):
                    call_str = self._attr_to_string(func)
                    if call_str in self._FORBIDDEN_ATTR_CALLS:
                        forbidden_calls.append(call_str)
                        issues.append(f"forbidden call: {call_str}()")

        passed = len(forbidden_calls) == 0 and len(forbidden_imports) == 0
        return SafetyReport(
            passed=passed,
            issues=issues,
            forbidden_calls=forbidden_calls,
            forbidden_imports=forbidden_imports,
        )

    def check_skill_file(self, file_path: str) -> SafetyReport:
        """Read *file_path* and run check_code on its contents."""
        code = Path(file_path).read_text()
        return self.check_code(code)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _attr_to_string(attr_node: ast.Attribute) -> str:
        """Reconstruct ``module.attr`` string from an ast.Attribute node.

        Handles nested attributes (e.g. ``os.path.join``) by recursing into
        the ``value`` field, falling back to ``ast.Name.id`` or a wildcard.
        """
        attr_name = attr_node.attr
        value = attr_node.value
        if isinstance(value, ast.Name):
            return f"{value.id}.{attr_name}"
        if isinstance(value, ast.Attribute):
            return f"{SafetyChecker._attr_to_string(value)}.{attr_name}"
        # Fallback for complex expressions — just return the attr name.
        return attr_name


# ---------------------------------------------------------------------------
# SkillVersionManager
# ---------------------------------------------------------------------------


class SkillVersionManager:
    """Track per-skill versions and git commit history for rollback."""

    _VERSION_PATTERN = re.compile(r"#\s*VERSION:\s*(\d+\.\d+\.\d+)")

    def __init__(self, skills_dir: str | None = None) -> None:
        self.skills_dir = Path(skills_dir) if skills_dir else Path("skills")
        if not self.skills_dir.exists():
            self.skills_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_version(self, skill_name: str) -> str:
        """Read the version from a VERSION comment, defaulting to '1.0.0'."""
        skill_path = self._skill_path(skill_name)
        if not skill_path.exists():
            return "1.0.0"
        content = skill_path.read_text()
        match = self._VERSION_PATTERN.search(content)
        if match:
            return match.group(1)
        return "1.0.0"

    def bump_version(self, skill_name: str) -> str:
        """Increment the minor version and return the new version string.

        If the skill file exists and has a VERSION comment, the comment is
        updated in-place.  If not, the version is tracked in memory only and
        the new string is returned.
        """
        current = self.get_version(skill_name)
        parts = current.split(".")
        if len(parts) == 3:
            major, minor, patch = parts
            new_version = f"{major}.{int(minor) + 1}.{patch}"
        else:
            new_version = "1.1.0"

        # Persist to file if the skill file exists.
        skill_path = self._skill_path(skill_name)
        if skill_path.exists():
            content = skill_path.read_text()
            new_content = self._VERSION_PATTERN.sub(
                f"# VERSION: {new_version}", content
            )
            if not self._VERSION_PATTERN.search(content):
                # No existing comment — prepend one.
                new_content = f"# VERSION: {new_version}\n{content}"
            skill_path.write_text(new_content)

        return new_version

    def get_history(self, skill_name: str) -> list:
        """Return git log history for the skill file as a list of dicts.

        Each dict has keys: ``commit`` (sha), ``message`` (str), ``date`` (str).
        Falls back to an empty list if git is unavailable or the file isn't
        tracked yet.
        """
        skill_path = self._skill_path(skill_name)
        try:
            proc = subprocess.run(
                [
                    "git",
                    "log",
                    "--pretty=format:%H|%s|%ci",
                    "--",
                    str(skill_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:
            return []

        if proc.returncode != 0:
            return []

        history: list = []
        for line in proc.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                history.append(
                    {
                        "commit": parts[0],
                        "message": parts[1],
                        "date": parts[2],
                    }
                )
        return history

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _skill_path(self, skill_name: str) -> Path:
        return self.skills_dir / f"{skill_name}.py"