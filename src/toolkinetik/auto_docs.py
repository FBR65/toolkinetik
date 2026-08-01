"""Auto-documentation for promoted skills.

Task 5.3: DocUpdater scans the skills directory, extracts function metadata
(name, docstring, arguments, return type) from each ``.py`` file via AST,
and generates a markdown table for ``docs/skills.md`` and README.md.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from toolkinetik.config import get_settings
from toolkinetik.db import SkillStore


# ---------------------------------------------------------------------------
# SkillInfo dataclass
# ---------------------------------------------------------------------------


@dataclass
class SkillInfo:
    """Extracted metadata for a single skill module."""

    module_name: str
    functions: list = field(default_factory=list)  # list of {"name","docstring","args","return_type"}


# ---------------------------------------------------------------------------
# DocUpdater
# ---------------------------------------------------------------------------


class DocUpdater:
    """Scan skills and generate markdown documentation tables."""

    def __init__(
        self,
        skills_dir: Optional[str] = None,
        db: Optional[SkillStore] = None,
        docs_dir: str = "docs",
    ) -> None:
        settings = get_settings()
        self.skills_dir = (
            skills_dir if skills_dir is not None else str(settings.skills_path)
        )
        self.db = db
        self.docs_dir = docs_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_skill_docs(self) -> str:
        """Scan all skills, extract info, write docs/skills.md, return markdown."""
        skill_infos: List[SkillInfo] = []
        skills_path = Path(self.skills_dir)
        if skills_path.exists():
            for py_file in sorted(skills_path.glob("*.py")):
                if py_file.name.startswith("__"):
                    continue
                info = self._extract_skill_info(str(py_file))
                skill_infos.append(info)

        markdown = self.update_readme_table(skill_infos)

        # Write to docs/skills.md
        docs_path = Path(self.docs_dir)
        docs_path.mkdir(parents=True, exist_ok=True)
        (docs_path / "skills.md").write_text(markdown)

        return markdown

    def update_readme_table(self, skill_infos: list) -> str:
        """Generate a markdown table from *skill_infos*.

        Returns the markdown table string (with header + separator + rows).
        """
        lines = [
            "# Skill Documentation",
            "",
            "| Module | Function | Args | Return Type | Description |",
            "|--------|----------|------|-------------|-------------|",
        ]

        for info in skill_infos:
            if not info.functions:
                lines.append(
                    f"| {info.module_name} | _(none)_ | | | |"
                )
            for func in info.functions:
                name = func.get("name", "")
                args = func.get("args", "")
                return_type = func.get("return_type", "")
                docstring = (func.get("docstring") or "").replace("\n", " ").strip()
                # Escape pipe characters in markdown table cells.
                args = str(args).replace("|", "\\|")
                return_type = str(return_type).replace("|", "\\|")
                docstring = docstring.replace("|", "\\|")
                lines.append(
                    f"| {info.module_name} | {name} | {args} | {return_type} | {docstring} |"
                )

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # AST extraction
    # ------------------------------------------------------------------

    def _extract_skill_info(self, file_path: str) -> SkillInfo:
        """AST-parse *file_path* and extract function metadata."""
        path = Path(file_path)
        module_name = path.stem

        try:
            source = path.read_text()
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            return SkillInfo(module_name=module_name, functions=[])

        functions: list = []
        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # Skip private/dunder functions
            if node.name.startswith("_"):
                continue

            func_info = {
                "name": node.name,
                "docstring": ast.get_docstring(node) or "",
                "args": self._format_args(node),
                "return_type": self._format_return_type(node),
            }
            functions.append(func_info)

        return SkillInfo(module_name=module_name, functions=functions)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_args(node) -> str:
        """Format the argument list of a function node as a string."""
        parts: list = []

        # Positional / standard arguments
        for arg in node.args.args:
            parts.append(arg.arg)

        # *args
        if node.args.vararg:
            parts.append(f"*{node.args.vararg.arg}")

        # Keyword-only arguments
        for arg in node.args.kwonlyargs:
            parts.append(f"{arg.arg}")

        # **kwargs
        if node.args.kwarg:
            parts.append(f"**{node.args.kwarg.arg}")

        return ", ".join(parts)

    @staticmethod
    def _format_return_type(node) -> str:
        """Extract the return type annotation as a string, or empty string."""
        if node.returns is None:
            return ""
        try:
            return ast.unparse(node.returns)
        except Exception:
            return ""