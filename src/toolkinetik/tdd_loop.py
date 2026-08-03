"""Automated TDD loop with sandbox execution and static security checks.

Task 3.2: TDDLoop pushes generated code + tests into the Docker sandbox,
collects results, retries on failure (up to ``max_retries``), and runs an
AST-based security scan before declaring success.

Security checks are delegated to :class:`SafetyChecker` from ``safety.py``
which checks both forbidden calls and forbidden imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from toolkinetik.safety import SafetyChecker, SafetyReport
from toolkinetik.sandbox import SandboxRunner

if TYPE_CHECKING:
    from toolkinetik.coding_agent import CodingAgent, SkillSpec


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SecurityResult:
    """Outcome of the static security scan."""

    passed: bool
    issues: list[str] = field(default_factory=list)


@dataclass
class TDDResult:
    """Final outcome of a TDD loop run."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    security_passed: bool
    security_issues: list[str] = field(default_factory=list)
    attempts: int = 0
    error: str = ""


class TDDLoop:
    """Run generated code through sandbox tests + security checks with retries.

    On test failure, if a :class:`CodingAgent` is provided, the loop generates
    a debugging prompt from the traceback, calls the coding agent for revised
    code, and retries with the new code.  This implements the retry-feedback
    loop described in Task 4.
    """

    def __init__(
        self,
        sandbox: SandboxRunner,
        max_retries: int = 3,
        coding_agent: CodingAgent | None = None,
    ) -> None:
        self.sandbox = sandbox
        self.max_retries = max_retries
        self.coding_agent = coding_agent
        self._safety_checker = SafetyChecker()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, spec: SkillSpec, code: str, tests: str) -> TDDResult:
        """Execute the TDD loop for *spec*.

        Pushes *code* + *tests* to the sandbox repeatedly until tests pass or
        ``max_retries`` is exhausted.  On success, runs the security scan and
        only returns ``success=True`` if both tests and security pass.

        When a :class:`CodingAgent` is wired in, test failures trigger a
        debugging prompt that asks the agent for revised code.  The revised
        code is then re-tested.
        """
        attempts = 0
        last_result: dict = {"exit_code": -1, "stdout": "", "stderr": ""}
        error_msg = ""
        current_code = code
        current_tests = tests

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            result = self.sandbox.run_tests(test_code=current_tests, skill_code=current_code)
            last_result = result
            exit_code = int(result.get("exit_code", -1))
            stdout = str(result.get("stdout", ""))
            stderr = str(result.get("stderr", ""))

            if exit_code == 0:
                # Tests passed — run security check via SafetyChecker.
                sec = self._security_check(current_code)
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

            # If we have a coding_agent and this isn't the last attempt,
            # generate revised code using the debugging prompt.
            if self.coding_agent is not None and attempt < self.max_retries:
                revised = self._get_revised_code(spec, error_msg, current_code)
                if revised is not None:
                    current_code = revised

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
    # Security check — delegated to SafetyChecker
    # ------------------------------------------------------------------

    def _security_check(self, code: str) -> SecurityResult:
        """Run the SafetyChecker on *code* and convert to SecurityResult."""
        report: SafetyReport = self._safety_checker.check_code(code)
        return SecurityResult(
            passed=report.passed,
            issues=list(report.issues),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_revised_code(
        self, spec: SkillSpec, error_trace: str, current_code: str
    ) -> str | None:
        """Ask the coding agent for revised code based on the error trace.

        Returns the revised code string, or None if the agent couldn't
        produce it.
        """
        if self.coding_agent is None:
            return None
        return self.coding_agent.revise_code(current_code, error_trace, spec)

    @staticmethod
    def _extract_traceback(stdout: str, stderr: str) -> str:
        """Best-effort extraction of a useful error message from test output."""
        combined = f"{stderr}\n{stdout}".strip()
        if not combined:
            return "tests failed (no output)"
        # Return the last few non-empty lines.
        lines = [ln for ln in combined.splitlines() if ln.strip()]
        return "\n".join(lines[-5:]) if lines else combined