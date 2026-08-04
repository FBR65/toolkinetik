"""Tests that README has no duplicate sections (#22)."""

from __future__ import annotations

import re
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"
TEXT = README.read_text()


def _count_section(title: str) -> int:
    return len(re.findall(rf"^##+\s+{re.escape(title)}\s*$", TEXT, re.MULTILINE))


class TestReadmeNoDupes:
    def test_prerequisites_once(self):
        assert _count_section("Prerequisites") <= 1

    def test_tech_stack_once(self):
        assert _count_section("Tech Stack") <= 1

    def test_quick_start_once(self):
        assert _count_section("Quick Start") <= 1

    def test_installation_once(self):
        assert _count_section("Installation") <= 1

    def test_content_preserved(self):
        for term in ["Agno", "IntentEngine", "SkillWriter", "Docker", "wigolo",
                     "RAG", "FastAPI", "NiceGUI", "Typer"]:
            assert term in TEXT, f"README must still mention {term}"