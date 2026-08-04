"""Tests that dead code has been removed (#19).

SPEC: docs/SPEC-25-improvements.md #19
Tier 1 — verify that unused/duplicate symbols are gone from src/.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src" / "toolkinetik"


def _source(module: str) -> str:
    return (SRC_DIR / f"{module}.py").read_text()


class TestDeadCodeRemoved:
    def test_safety_no_unused_FORBIDDEN_CALLS(self):
        # FORBIDDEN_CALLS was an unused duplicate of _FORBIDDEN_ATTR_CALLS.
        src = _source("safety")
        # Either it's gone entirely, or only the canonical sets remain.
        assert not re.search(r"^\s*FORBIDDEN_CALLS\s*=", src, re.MULTILINE), (
            "FORBIDDEN_CALLS is dead code (duplicate of _FORBIDDEN_ATTR_CALLS)"
        )

    def test_app_no_get_intent_engine_internal_dup(self):
        src = _source("app")
        assert "_get_intent_engine" not in src, (
            "_get_intent_engine is an unused duplicate of get_intent_engine"
        )

    def test_skill_writer_no_stdin_to_error(self):
        src = _source("skill_writer")
        assert "stdin_to_error" not in src, "stdin_to_error is a no-op helper"

    def test_intent_no_legacy_classes(self):
        # Removed in #8 (pipeline consolidation); until then this stays.
        # For #19 we only assert that the two helper symbols above are gone.
        pass


class TestImportsStillWork:
    def test_can_import_app(self):
        import toolkinetik.app  # noqa: F401

    def test_can_import_safety(self):
        import toolkinetik.safety  # noqa: F401

    def test_can_import_skill_writer(self):
        import toolkinetik.skill_writer  # noqa: F401