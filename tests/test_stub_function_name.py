"""Tests for SkillWriter stub code/tests using spec.name (#18).

SPEC: docs/SPEC-25-improvements.md #18
Tier 2 — _stub_code must define `def {spec.name}():`, not `def test_function():`.
_stub_tests must import {spec.name} from skill.
"""

from __future__ import annotations

import ast

from toolkinetik.coding_agent import SkillSpec
from toolkinetik.skill_writer import SkillWriter


def _make_writer(tmp_path) -> SkillWriter:
    from unittest.mock import MagicMock
    return SkillWriter(registry=MagicMock(), db=MagicMock(), skills_dir=str(tmp_path))


def _first_function_name(code: str) -> str:
    tree = ast.parse(code)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            return node.name
    return ""


class TestStubCodeUsesSpecName:
    def test_stub_code_defines_spec_name(self, tmp_path):
        writer = _make_writer(tmp_path)
        spec = SkillSpec(name="fibonacci", description="d", signature="def fibonacci():")
        code = writer._stub_code(spec)
        assert "def fibonacci(" in code
        assert "def test_function(" not in code
        assert _first_function_name(code) == "fibonacci"

    def test_stub_tests_import_spec_name(self, tmp_path):
        writer = _make_writer(tmp_path)
        spec = SkillSpec(name="fibonacci", description="d", signature="def fibonacci():")
        tests = writer._stub_tests(spec)
        assert "from skill import fibonacci" in tests
        assert "fibonacci()" in tests
        assert "test_function" not in tests

    def test_stub_code_ast_valid(self, tmp_path):
        writer = _make_writer(tmp_path)
        spec = SkillSpec(name="valid_name", description="d", signature="def valid_name():")
        code = writer._stub_code(spec)
        ast.parse(code)  # raises if invalid

    def test_stub_tests_ast_valid(self, tmp_path):
        writer = _make_writer(tmp_path)
        spec = SkillSpec(name="valid_name", description="d", signature="def valid_name():")
        tests = writer._stub_tests(spec)
        ast.parse(tests)

    def test_stub_code_with_different_name(self, tmp_path):
        writer = _make_writer(tmp_path)
        spec = SkillSpec(name="pdf_to_markdown", description="d", signature="def pdf_to_markdown():")
        code = writer._stub_code(spec)
        assert "def pdf_to_markdown(" in code