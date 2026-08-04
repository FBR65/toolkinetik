"""Tests for pyproject.toml dependency consolidation (#21).

SPEC: docs/SPEC-25-improvements.md #21
Tier 1 — agno must be pinned; dev deps must not be split across sections.
"""

from __future__ import annotations

import re
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
TEXT = PYPROJECT.read_text()


def _section(name: str) -> str:
    m = re.search(rf"\[{re.escape(name)}\]\s*(.*?)(?=\n\[|\Z)", TEXT, re.DOTALL)
    return m.group(1) if m else ""


class TestPyprojectDeps:
    def test_agno_pinned(self):
        # Find the agno line in [project] dependencies and check for a version pin.
        deps = _section("project")
        # The dependencies list is in the [project] section before [project.optional-dependencies].
        m = re.search(r'"agno([<>=!~][^"]*)?"', deps)
        assert m, "agno must be in dependencies"
        pin = m.group(1) or ""
        assert pin, "agno must be version-pinned, got bare 'agno'"

    def test_dev_deps_not_duplicated_across_sections(self):
        # The optional-dependencies block is multi-line; extract the dev sub-block.
        opt_block = re.search(r"\[project\.optional-dependencies\]\s*(.*?)(?=\n\[|\Z)", TEXT, re.DOTALL)
        assert opt_block
        opt_text = opt_block.group(1)
        dev_block = re.search(r'dev\s*=\s*\[(.*?)\]', opt_text, re.DOTALL)
        depgroups_block = re.search(r'\[dependency-groups\]\s*(.*?)(?=\n\[|\Z)', TEXT, re.DOTALL)
        depgroups_text = depgroups_block.group(1) if depgroups_block else ""
        dg_dev_block = re.search(r'dev\s*=\s*\[(.*?)\]', depgroups_text, re.DOTALL)

        # pytest-cov and pytest-randomly must appear in at most one of the two dev sections.
        for pkg in ["pytest-cov", "pytest-randomly"]:
            in_opt = dev_block and pkg in (dev_block.group(1) if dev_block else "")
            in_dg = dg_dev_block and pkg in (dg_dev_block.group(1) if dg_dev_block else "")
            assert not (in_opt and in_dg), f"{pkg} duplicated in both dev sections"

    def test_rag_extra_present(self):
        opt_block = re.search(r"\[project\.optional-dependencies\]\s*(.*?)(?=\n\[|\Z)", TEXT, re.DOTALL)
        assert opt_block
        assert "rag" in opt_block.group(1)
        rag_block = re.search(r'rag\s*=\s*\[(.*?)\]', opt_block.group(1), re.DOTALL)
        assert rag_block
        rag_text = rag_block.group(1)
        assert "lancedb" in rag_text
        assert "sentence-transformers" in rag_text