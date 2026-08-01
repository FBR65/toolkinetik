"""Automated TDD loop with sandbox execution and static security checks.

Task 3.2: TDDLoop pushes generated code + tests into the Docker sandbox,
collects results, retries on failure (up to ``max_retries``), and runs an
AST-based security scan before declaring success.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import List

from agno_agent_os.coding_agent import SkillSpec
from agno_agent_os.sandbox import SandboxRunner


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SecurityResult:
    """Outcome of the static security scan."""

    passed: bool
    issues: list = field(default_factory=list)


@dataclass
class TDDResult:
    """Final outcome of a TDD loop run."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    security_passed: bool
    security_issues: list = field(default_factory=list)
    attempts: int = 0
    error: str = ""


# ---------------------------------------------------------------------------
# Forbidden-call detection
# ---------------------------------------------------------------------------

# Call patterns flagged as unsafe.  Each entry is (module_attr_or_builtin, kind).
# kind: "attr"  -> matches Name(func='X') where X is a builtin (eval/exec)
#         "call" -> matches ast.Call whose func is an Attribute with attr == X
_FORBIDDEN_BUILTINS = {"eval", "exec", "__import__"}
_FORBIDDEN_ATTRS = {"system"}  # os.system — matched via Attribute attr
_FORBIDDEN_MODULES_ATTRS = {
    "system",  # os.system
    "popen",   # os.popen
}
# subprocess.* — any attribute access on a name "subprocess" is flagged.
_FORBIDDEN_MODULE_NAMES = {"subprocess"}


class TDDLoop:
    """Run generated code through sandbox tests + security checks with retries."""

    def __init__(self, sandbox: SandboxRunner, max_retries: int = 3) -> None:
        self.sandbox = sandbox
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, spec: SkillSpec, code: str, tests: str) -> TDDResult:
        """Execute the TDD loop for *spec*.

        Pushes *code* + *tests* to the sandbox repeatedly until tests pass or
        ``max_retries`` is exhausted.  On success, runs the security scan and
        only returns ``success=True`` if both tests and security pass.
        """
        attempts = 0
        last_result: dict = {"exit_code": -1, "stdout": "", "stderr": ""}
        error_msg = ""

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            result = self.sandbox.run_tests(test_code=tests, skill_code=code)
            last_result = result
            exit_code = int(result.get("exit_code", -1))
            stdout = str(result.get("stdout", ""))
            stderr = str(result.get("stderr", ""))

            if exit_code == 0:
                # Tests passed — run security check.
                sec = self._security_check(code)
                return TDDResult(
                    success=sec.passed,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    security_passed=sec.passed,
                    security_issues=sec.issues,
                    attempts=attempts,
                    error="" if sec.passed else "; ".join(sec.issues),
                )
            # Tests failed — capture traceback for the retry hint.
            error_msg = self._extract_traceback(stdout, stderr)

        # Exhausted retries.
        return TDDResult(
            success=False,
            exit_code=int(last_result.get("exit_code", -1)),
            stdout=str(last_result.get("stdout", "")),
            stderr=str(last_result.get("stderr", "")),
            security_passed=False,
            security_issues=[],
            attempts=attempts,
            error=error_msg,
        )

    # ------------------------------------------------------------------
    # Security check
    # ------------------------------------------------------------------

    def _security_check(self, code: str) -> SecurityResult:
        """AST-parse *code* and flag forbidden calls.

        Forbidden:
          - ``os.system(...)``, ``os.popen(...)``
          - any ``subprocess.<anything>``
          - builtins: ``eval``, ``exec``, ``__import__``
        """
        issues: List[str] = []
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return SecurityResult(passed=False, issues=[f"syntax error: {exc}"])

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Direct builtin call: eval(...), exec(...), __import__(...)
                if isinstance(func, ast.Name) and func.id in _FORBIDDEN_BUILTINS:
                    issues.append(f"forbidden builtin call: {func.id}()")
                    continue
                # Attribute call: os.system(...), subprocess.run(...), etc.
                if isinstance(func, ast.Attribute):
                    attr = func.attr
                    # subprocess.* — flag by module name if value is a Name.
                    value = func.value
                    if isinstance(value, ast.Name) and value.id in _FORBIDDEN_MODULE_NAMES:
                        issues.append(f"forbidden call: {value.id}.{attr}()")
                        continue
                    # os.system / os.popen — flag as os.<attr> when value is "os".
                    if isinstance(value, ast.Name) and value.id == "os" and attr in _FORBIDDEN_ATTRS:
                        issues.append(f"forbidden call: os.{attr}()")
                        continue
                    # Fallback: flag by attribute name alone (covers aliases).
                    if attr in _FORBIDDEN_ATTRS:
                        issues.append(f"forbidden call: .{attr}()")
                        continue

        return SecurityResult(passed=len(issues) == 0, issues=issues)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_traceback(stdout: str, stderr: str) -> str:
        """Best-effort extraction of a useful error message from test output."""
        combined = f"{stderr}\n{stdout}".strip()
        if not combined:
            return "tests failed (no output)"
        # Return the last few non-empty lines.
        lines = [ln for ln in combined.splitlines() if ln.strip()]
        return "\n".join(lines[-5:]) if lines else combined