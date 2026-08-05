"""Tests for SafetyChecker trusted-path for skill scripts (P0.7).

SPEC: docs/SPEC-production-readiness.md P0.7
Tier 3 — trusted skill scripts (in skills_dir/scripts/) must bypass the
import restrictions that apply to LLM-generated code.
"""

from __future__ import annotations

from toolkinetik.safety import SafetyChecker


class TestSafetyTrustedPath:
    def test_untrusted_code_with_os_import_blocked(self):
        """Default (untrusted): import os is blocked."""
        checker = SafetyChecker()
        report = checker.check_code("import os\nos.system('ls')")
        assert not report.passed

    def test_trusted_code_with_os_import_allowed(self):
        """Trusted path: import os is allowed (skill helper script)."""
        checker = SafetyChecker()
        report = checker.check_code("import os\nprint(os.getcwd())", trusted_path=True)
        assert report.passed

    def test_trusted_code_with_subprocess_allowed(self):
        """Trusted path: import subprocess is allowed."""
        checker = SafetyChecker()
        report = checker.check_code("import subprocess\nsubprocess.run(['ls'])", trusted_path=True)
        assert report.passed

    def test_trusted_code_still_blocks_eval(self):
        """Trusted path: eval() is still blocked (dangerous builtins)."""
        checker = SafetyChecker()
        report = checker.check_code("eval('1+1')", trusted_path=True)
        assert not report.passed
        assert "eval" in report.forbidden_calls

    def test_trusted_code_still_blocks_exec(self):
        """Trusted path: exec() is still blocked."""
        checker = SafetyChecker()
        report = checker.check_code("exec('print(1)')", trusted_path=True)
        assert not report.passed

    def test_trusted_code_still_blocks_os_system(self):
        """Trusted path: os.system() is still blocked (dangerous call)."""
        checker = SafetyChecker()
        report = checker.check_code("import os\nos.system('rm -rf /')", trusted_path=True)
        assert not report.passed
        assert "os.system" in report.forbidden_calls

    def test_trusted_code_blocks_compile(self):
        """Trusted path: compile() is still blocked."""
        checker = SafetyChecker()
        report = checker.check_code("compile('1+1', '<s>', 'eval')", trusted_path=True)
        assert not report.passed

    def test_trusted_code_allows_shutil(self):
        """Trusted path: import shutil is allowed (needed by skill scripts)."""
        checker = SafetyChecker()
        report = checker.check_code("import shutil\nshutil.copy('a', 'b')", trusted_path=True)
        assert report.passed

    def test_trusted_code_allows_ctypes(self):
        """Trusted path: import ctypes is allowed."""
        checker = SafetyChecker()
        report = checker.check_code("import ctypes", trusted_path=True)
        assert report.passed

    def test_default_trusted_path_is_false(self):
        """Default for trusted_path is False (safe by default)."""
        checker = SafetyChecker()
        report = checker.check_code("import os")
        assert not report.passed