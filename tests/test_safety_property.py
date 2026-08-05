"""Property-based tests for SafetyChecker (P3.8).

SPEC: docs/SPEC-production-readiness.md P3.8
Uses hypothesis to verify invariants of the SafetyChecker.
"""

from __future__ import annotations

import keyword

import pytest
from hypothesis import given
from hypothesis import strategies as st

from toolkinetik.safety import SafetyChecker

# Strategy for generating valid Python identifiers (not keywords)
identifiers = st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=10).filter(
    lambda s: (s[0].isalpha() or s[0] == "_") and not keyword.iskeyword(s)
)

# Strategy for simple safe code (just a function definition)
safe_code_strategy = st.builds(
    lambda name: f"def {name}():\n    return 0\n",
    identifiers.filter(lambda s: not s.startswith("__")),
)


class TestSafetyCheckerProperties:
    @given(code=safe_code_strategy)
    def test_safe_function_passes(self, code: str):
        """A simple function definition with no imports/calls always passes."""
        checker = SafetyChecker()
        report = checker.check_code(code)
        assert report.passed, f"safe code failed: {code} → {report.issues}"

    @given(code=safe_code_strategy)
    def test_check_code_is_idempotent(self, code: str):
        """check_code(code) called twice returns the same result."""
        checker = SafetyChecker()
        r1 = checker.check_code(code)
        r2 = checker.check_code(code)
        assert r1.passed == r2.passed
        assert r1.issues == r2.issues

    @given(code=st.builds(lambda: "import os\n"))
    def test_import_os_always_blocked(self, code: str):
        """import os is always blocked (untrusted)."""
        checker = SafetyChecker()
        report = checker.check_code(code)
        assert not report.passed

    @given(code=st.builds(lambda: "import os\n"))
    def test_import_os_allowed_in_trusted_path(self, code: str):
        """import os is always allowed in trusted_path."""
        checker = SafetyChecker()
        report = checker.check_code(code, trusted_path=True)
        assert report.passed

    @given(code=st.builds(lambda: "eval('1+1')\n"))
    def test_eval_always_blocked(self, code: str):
        """eval() is blocked even in trusted_path."""
        checker = SafetyChecker()
        report = checker.check_code(code, trusted_path=True)
        assert not report.passed

    @given(
        code=st.builds(
            lambda mod: f"import {mod}\n",
            st.sampled_from(["math", "json", "re", "datetime", "random"]),
        )
    )
    def test_allowed_stdlib_passes(self, code: str):
        """Allowed stdlib modules always pass."""
        checker = SafetyChecker()
        report = checker.check_code(code)
        assert report.passed, f"allowed stdlib failed: {code} → {report.issues}"

    @given(
        code=st.builds(
            lambda mod: f"import {mod}\n",
            st.sampled_from(["socket", "urllib", "http", "ftplib", "telnetlib"]),
        )
    )
    def test_disallowed_modules_blocked(self, code: str):
        """Disallowed modules are always blocked (untrusted)."""
        checker = SafetyChecker()
        report = checker.check_code(code)
        assert not report.passed

    @given(code=st.text(min_size=0, max_size=20))
    def test_never_raises_on_arbitrary_input(self, code: str):
        """check_code never raises an exception on any input."""
        checker = SafetyChecker()
        try:
            checker.check_code(code)
        except Exception:
            pytest.fail("check_code raised on arbitrary input")

    @given(code=st.builds(lambda: "x = 1\n"))
    def test_clean_code_has_empty_issues(self, code: str):
        """Clean code has no issues and no forbidden calls/imports."""
        checker = SafetyChecker()
        report = checker.check_code(code)
        assert report.passed
        assert report.issues == []
        assert report.forbidden_calls == []
        assert report.forbidden_imports == []