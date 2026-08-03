"""Tests for the safety checker and skill version manager."""

from __future__ import annotations

import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from toolkinetik.safety import SafetyChecker, SafetyReport, SkillVersionManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_tmp_file(content: str, suffix: str = ".py") -> tuple:
    """Write *content* to a temp file and return (tmpdir, path)."""
    tmpdir = TemporaryDirectory()
    p = Path(tmpdir.name) / f"skill{suffix}"
    p.write_text(content)
    return tmpdir, str(p)


# ---------------------------------------------------------------------------
# SafetyChecker — clean code & forbidden calls
# ---------------------------------------------------------------------------


class TestSafetyCleanCode:
    def test_safety_clean_code(self):
        checker = SafetyChecker()
        code = "def add(a, b):\n    return a + b\n"
        report = checker.check_code(code)
        assert isinstance(report, SafetyReport)
        assert report.passed is True
        assert report.forbidden_calls == []
        assert report.forbidden_imports == []

    def test_safety_syntax_error(self):
        checker = SafetyChecker()
        code = "def add(a, b\n  return a + b\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert any("syntax error" in i for i in report.issues)


class TestSafetyForbiddenCalls:
    def test_safety_os_system(self):
        checker = SafetyChecker()
        code = "import os\nos.system('echo hi')\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert "os.system" in report.forbidden_calls

    def test_safety_subprocess(self):
        checker = SafetyChecker()
        code = "import subprocess\nsubprocess.run(['ls'])\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert "subprocess.run" in report.forbidden_calls

    def test_safety_eval(self):
        checker = SafetyChecker()
        code = "x = eval('1+1')\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert "eval" in report.forbidden_calls

    def test_safety_exec(self):
        checker = SafetyChecker()
        code = "exec('print(1)')\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert "exec" in report.forbidden_calls

    def test_safety_compile(self):
        checker = SafetyChecker()
        code = "c = compile('1+1', '<s>', 'eval')\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert "compile" in report.forbidden_calls

    def test_safety_import_function(self):
        checker = SafetyChecker()
        code = "m = __import__('os')\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert "__import__" in report.forbidden_calls

    def test_attr_to_string_nested_attribute(self):
        """_attr_to_string recurses into nested attributes (os.path.join)."""
        tree = ast.parse("os.path.join('a')")
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert SafetyChecker._attr_to_string(call.func) == "os.path.join"

    def test_attr_to_string_fallback(self):
        """_attr_to_string falls back to the bare attr for complex expressions."""
        # `"x".join(...)` — the attribute's value is a Constant, not Name/Attribute.
        tree = ast.parse('",".join(parts)')
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
        assert SafetyChecker._attr_to_string(call.func) == "join"


# ---------------------------------------------------------------------------
# SafetyChecker — forbidden imports
# ---------------------------------------------------------------------------


class TestSafetyForbiddenImports:
    def test_safety_forbidden_import_os(self):
        checker = SafetyChecker()
        code = "import os\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert any("os" in fi for fi in report.forbidden_imports)

    def test_safety_forbidden_import_subprocess(self):
        checker = SafetyChecker()
        code = "import subprocess\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert any("subprocess" in fi for fi in report.forbidden_imports)

    def test_safety_forbidden_from_import(self):
        checker = SafetyChecker()
        code = "from os import path\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert any("os" in fi for fi in report.forbidden_imports)

    def test_safety_allowed_import(self):
        checker = SafetyChecker()
        code = "import json\n"
        report = checker.check_code(code)
        assert report.passed is True


# ---------------------------------------------------------------------------
# SafetyChecker — whitelist-based import allowlisting (B1)
# ---------------------------------------------------------------------------


class TestSafetyWhitelistImports:
    def test_whitelist_allows_stdlib_math(self):
        checker = SafetyChecker()
        code = "import math\ndef f():\n    return math.sqrt(4)\n"
        report = checker.check_code(code)
        assert report.passed is True

    def test_whitelist_allows_json(self):
        checker = SafetyChecker()
        report = checker.check_code("import json\n")
        assert report.passed is True

    def test_whitelist_blocks_socket(self):
        checker = SafetyChecker()
        code = "import socket\ns = socket.socket()\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert any("socket" in fi for fi in report.forbidden_imports)

    def test_whitelist_blocks_urllib(self):
        checker = SafetyChecker()
        code = "import urllib.request\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert any("urllib" in fi for fi in report.forbidden_imports)

    def test_whitelist_blocks_pathlib(self):
        checker = SafetyChecker()
        code = "import pathlib\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert any("pathlib" in fi for fi in report.forbidden_imports)

    def test_whitelist_blocks_disallowed_from_import(self):
        """From-import of a disallowed module must be flagged (B1)."""
        checker = SafetyChecker()
        code = "from urllib import request\n"
        report = checker.check_code(code)
        assert report.passed is False
        assert any("urllib" in fi for fi in report.forbidden_imports)
        assert any("disallowed import" in i for i in report.issues)

    def test_whitelist_allows_stdlib_from_import(self):
        """From-import of an allowed stdlib module must pass (B1)."""
        checker = SafetyChecker()
        code = "from math import sqrt\n"
        report = checker.check_code(code)
        assert report.passed is True

    def test_whitelist_allows_relative_skill_import(self):
        checker = SafetyChecker()
        code = "from .math_skill import calculate_fibonacci\n"
        report = checker.check_code(code)
        assert report.passed is True


# ---------------------------------------------------------------------------
# SafetyChecker — check_skill_file
# ---------------------------------------------------------------------------


class TestSafetyCheckSkillFile:
    def test_safety_check_skill_file_clean(self):
        checker = SafetyChecker()
        tmpdir, path = _write_tmp_file("def add(a, b):\n    return a + b\n")
        try:
            report = checker.check_skill_file(path)
            assert report.passed is True
        finally:
            tmpdir.cleanup()

    def test_safety_check_skill_file_forbidden(self):
        checker = SafetyChecker()
        tmpdir, path = _write_tmp_file("import os\nos.system('rm -rf /')\n")
        try:
            report = checker.check_skill_file(path)
            assert report.passed is False
            assert "os.system" in report.forbidden_calls
        finally:
            tmpdir.cleanup()


# ---------------------------------------------------------------------------
# SkillVersionManager
# ---------------------------------------------------------------------------


class TestSkillVersionManager:
    def test_version_manager_default(self):
        """get_version returns '1.0.0' for a skill with no VERSION comment."""
        with TemporaryDirectory() as d:
            vm = SkillVersionManager(skills_dir=d)
            # No file exists yet.
            assert vm.get_version("newskill") == "1.0.0"

            # File exists but no VERSION comment.
            (Path(d) / "newskill.py").write_text("def newskill(): pass\n")
            assert vm.get_version("newskill") == "1.0.0"

    def test_version_manager_reads_version_comment(self):
        with TemporaryDirectory() as d:
            (Path(d) / "vskill.py").write_text(
                "# VERSION: 2.3.1\ndef vskill(): pass\n"
            )
            vm = SkillVersionManager(skills_dir=d)
            assert vm.get_version("vskill") == "2.3.1"

    def test_version_manager_bump(self):
        with TemporaryDirectory() as d:
            (Path(d) / "bskill.py").write_text(
                "# VERSION: 1.0.0\ndef bskill(): pass\n"
            )
            vm = SkillVersionManager(skills_dir=d)
            new = vm.bump_version("bskill")
            assert new == "1.1.0"
            # Verify the file was updated.
            assert vm.get_version("bskill") == "1.1.0"

    def test_version_manager_bump_no_comment(self):
        """bump_version on a file without a VERSION comment adds one."""
        with TemporaryDirectory() as d:
            (Path(d) / "noskill.py").write_text("def noskill(): pass\n")
            vm = SkillVersionManager(skills_dir=d)
            new = vm.bump_version("noskill")
            assert new == "1.1.0"
            assert vm.get_version("noskill") == "1.1.0"

    def test_version_manager_bump_multiple(self):
        with TemporaryDirectory() as d:
            (Path(d) / "mskill.py").write_text(
                "# VERSION: 1.0.0\ndef mskill(): pass\n"
            )
            vm = SkillVersionManager(skills_dir=d)
            assert vm.bump_version("mskill") == "1.1.0"
            assert vm.bump_version("mskill") == "1.2.0"
            assert vm.bump_version("mskill") == "1.3.0"

    def test_version_manager_history(self):
        """get_history uses git log — mock subprocess.run."""
        with TemporaryDirectory() as d:
            (Path(d) / "hskill.py").write_text("def hskill(): pass\n")
            vm = SkillVersionManager(skills_dir=d)

            git_output = (
                "abc1234|feat: add hskill|2025-01-15 10:00:00 +0000\n"
                "def5678|fix: hskill bug|2025-01-14 12:00:00 +0000"
            )
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = git_output

            with patch(
                "toolkinetik.safety.subprocess.run",
                return_value=mock_proc,
            ) as mock_run:
                history = vm.get_history("hskill")

            assert mock_run.called
            assert len(history) == 2
            assert history[0]["commit"] == "abc1234"
            assert history[0]["message"] == "feat: add hskill"
            assert history[0]["date"] == "2025-01-15 10:00:00 +0000"
            assert history[1]["commit"] == "def5678"
            assert history[1]["message"] == "fix: hskill bug"

    def test_version_manager_history_empty(self):
        """get_history returns empty list when git returns non-zero."""
        with TemporaryDirectory() as d:
            (Path(d) / "empty.py").write_text("def empty(): pass\n")
            vm = SkillVersionManager(skills_dir=d)

            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout = ""

            with patch(
                "toolkinetik.safety.subprocess.run",
                return_value=mock_proc,
            ):
                history = vm.get_history("empty")
            assert history == []

    def test_version_manager_creates_dir(self):
        """SkillVersionManager creates the skills dir when missing."""
        with TemporaryDirectory() as d:
            sub = Path(d) / "nested" / "skills"
            assert not sub.exists()
            SkillVersionManager(skills_dir=str(sub))
            assert sub.exists()

    def test_version_manager_bump_non_semver(self):
        """bump_version falls back to 1.1.0 when the version isn't 3-part."""
        with TemporaryDirectory() as d:
            (Path(d) / "weird.py").write_text("# VERSION: 2\ndef weird(): pass\n")
            vm = SkillVersionManager(skills_dir=d)
            # Force get_version to return a malformed, non-3-part value.
            with patch.object(vm, "get_version", return_value="2"):
                assert vm.bump_version("weird") == "1.1.0"

    def test_version_manager_history_git_error(self):
        """get_history returns empty list when git raises."""
        with TemporaryDirectory() as d:
            (Path(d) / "err.py").write_text("def err(): pass\n")
            vm = SkillVersionManager(skills_dir=d)

            with patch(
                "toolkinetik.safety.subprocess.run",
                side_effect=OSError("no git"),
            ):
                history = vm.get_history("err")
            assert history == []


# ---------------------------------------------------------------------------
# SkillVersionManager — path traversal protection (B4)
# ---------------------------------------------------------------------------


class TestSkillVersionManagerTraversal:
    def test_get_version_blocks_traversal(self):
        """get_version must not resolve a name escaping the skills dir."""
        with TemporaryDirectory() as d:
            vm = SkillVersionManager(skills_dir=d)
            # The naive join skills_dir/"../outside/evil.py" resolves to
            # parent/outside/evil.py — which we plant here. Current code reads
            # it and returns its VERSION comment; the fix must not.
            outside = Path(d).parent / "outside" / "evil.py"
            outside.parent.mkdir(parents=True, exist_ok=True)
            outside.write_text("# VERSION: 9.9.9\ndef evil(): pass\n")
            assert vm.get_version("../outside/evil") == "1.0.0"

    def test_bump_version_blocks_traversal(self):
        """bump_version must not write outside the skills dir."""
        with TemporaryDirectory() as d:
            outside = Path(d).parent / "outside" / "evil.py"
            outside.parent.mkdir(parents=True, exist_ok=True)
            outside.write_text("# VERSION: 1.0.0\noriginal\n")

            vm = SkillVersionManager(skills_dir=d)
            # Traversal targeting the outside file — must not modify it.
            vm.bump_version("../outside/evil")
            assert outside.read_text() == "# VERSION: 1.0.0\noriginal\n"
            assert vm.get_version("../outside/evil") == "1.0.0"