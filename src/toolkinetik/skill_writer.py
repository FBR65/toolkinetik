"""SkillWriter: the meta-skill that generates, tests, and registers new skills.

Uses wigolo (MCP) for research, an LLM for code generation, Docker sandbox for TDD,
AST-based SafetyChecker for security validation, and DynamicToolRegistry for hot-reload.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from toolkinetik.coding_agent import SkillSpec
from toolkinetik.config import get_settings
from toolkinetik.db import SkillStore
from toolkinetik.promotion import safe_skill_path
from toolkinetik.registry import DynamicToolRegistry
from toolkinetik.safety import SafetyChecker, SafetyReport


@dataclass
class TDDResult:
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    attempts: int = 0


@dataclass
class PromoteResult:
    success: bool
    skill_path: str = ""
    error: str = ""
    git_committed: bool = False


@dataclass
class SkillWriterResult:
    success: bool
    spec: SkillSpec | None = None
    code: str = ""
    tests: str = ""
    tdd_result: TDDResult | None = None
    safety_passed: bool = False
    safety_issues: list[str] = field(default_factory=list)
    promotion: PromoteResult | None = None
    error: str = ""


class SkillWriter:
    """The meta-skill: creates, tests, validates, and registers new skills.

    Workflow:
      1. generate_spec(user_request) → SkillSpec
      2. _research_dependencies(spec) → wigolo research on PyPi/GitHub
      3. _generate_code(spec) → code + tests via LLM
      4. _safety_check(code) → AST-based SafetyChecker
      5. _run_tdd(code, tests) → Docker sandbox (TDDLoop)
      6. _promote(name, code, metadata) → Hot-Reload + Git + DB
    """

    def __init__(
        self,
        wigolo: Any = None,
        llm: Any = None,
        sandbox: Any = None,
        registry: DynamicToolRegistry | None = None,
        db: SkillStore | None = None,
        skills_dir: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self._wigolo = wigolo
        self._llm = llm
        self._sandbox = sandbox
        self._safety = SafetyChecker()
        self._max_retries = max_retries

        settings = get_settings()
        self._skills_dir = skills_dir if skills_dir else str(settings.skills_path)
        self._registry = registry if registry else DynamicToolRegistry(self._skills_dir)
        self._db = db if db else SkillStore(str(settings.db_full_path))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_skill(self, user_request: str) -> SkillWriterResult:
        """End-to-end: generate_spec → research → codegen → tdd → safety → promote."""
        spec = self.generate_spec(user_request)
        if spec is None:
            return SkillWriterResult(success=False, error="Could not generate skill spec")

        self._research_dependencies(spec)

        code, tests = self._generate_code(spec)
        if not code:
            return SkillWriterResult(
                success=False, spec=spec, error="Code generation failed"
            )

        safety = self._safety_check(code)
        if not safety.passed:
            return SkillWriterResult(
                success=False,
                spec=spec,
                code=code,
                safety_passed=False,
                safety_issues=safety.issues,
                error="Safety check failed: " + "; ".join(safety.issues),
            )

        tdd = self._run_tdd(code, tests)
        if not tdd.success:
            return SkillWriterResult(
                success=False,
                spec=spec,
                code=code,
                tests=tests,
                tdd_result=tdd,
                safety_passed=True,
                error=f"TDD failed after {tdd.attempts} attempts",
            )

        promo = self._promote(spec.name, code, {
            "description": spec.description,
            "signature": spec.signature,
        })
        if not promo.success:
            return SkillWriterResult(
                success=False,
                spec=spec,
                code=code,
                tdd_result=tdd,
                safety_passed=True,
                error=promo.error,
            )

        return SkillWriterResult(
            success=True,
            spec=spec,
            code=code,
            tests=tests,
            tdd_result=tdd,
            safety_passed=True,
            promotion=promo,
        )

    # ------------------------------------------------------------------
    # 1. Spec Generation
    # ------------------------------------------------------------------

    def generate_spec(self, user_request: str) -> SkillSpec | None:
        """Convert a natural-language request into a SkillSpec via LLM."""
        if self._llm is not None:
            spec_dict = self._llm_classify(user_request)
        else:
            spec_dict = self._heuristic_spec(user_request)

        name = spec_dict.get("name") or self._extract_skill_name(user_request)
        description = spec_dict.get("description", user_request)
        signature = spec_dict.get("signature", f"def {name}(*args, **kwargs):")
        test_cases = spec_dict.get("test_cases", [])

        return SkillSpec(
            name=name,
            description=description,
            signature=signature,
            test_cases=test_cases,
        )

    # ------------------------------------------------------------------
    # 2. wigolo Research
    # ------------------------------------------------------------------

    def _research_dependencies(self, spec: SkillSpec) -> str:
        """Use wigolo to research dependencies mentioned in the spec."""
        if self._wigolo is None:
            return ""

        packages = re.findall(r'import\s+(\w+)|\b([\w-]+)==', spec.description + spec.signature)
        keywords = set()
        for match in packages:
            for word in match:
                if word:
                    keywords.add(word.lower())

        search_term = spec.name.replace("_", " ")
        try:
            result = self._wigolo.research(
                query=f"Python library for {search_term}",
                context=f"Skill signature: {spec.signature}",
            )
            if isinstance(result, dict):
                result_str = json.dumps(result)
            else:
                result_str = str(result)
            return result_str
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # 3. Code Generation (TDD-first)
    # ------------------------------------------------------------------

    def _generate_code(self, spec: SkillSpec) -> tuple[str, str]:
        """Generate code + tests via LLM with TDD-first prompting."""
        if self._llm is None:
            return self._stub_code(spec), self._stub_tests(spec)

        prompt = self._build_tdd_prompt(spec)
        try:
            response = self._llm.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a Python TDD expert. "
                     "Always write tests first, then implementation. "
                     "Output ONLY the test code block, then the implementation code block."},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response.choices[0].message.content
            code, tests = self._parse_code_and_tests(raw)
            if code and tests:
                return code, tests
        except Exception:
            pass

        return self._stub_code(spec), self._stub_tests(spec)

    # ------------------------------------------------------------------
    # 4. Safety Check (AST)
    # ------------------------------------------------------------------

    def _safety_check(self, code: str) -> SafetyReport:
        """Run SafetyChecker on generated code."""
        return self._safety.check_code(code)

    # ------------------------------------------------------------------
    # 5. TDD Loop (Docker Sandbox)
    # ------------------------------------------------------------------

    def _run_tdd(self, code: str, tests: str) -> TDDResult:
        """Run tests in Docker sandbox with retry.
        Uses the Docker SandboxRunner if available, otherwise local fallback.
        """
        if self._sandbox is None:
            return self._run_local_tdd(code, tests)

        attempts = 0
        for attempt in range(1, self._max_retries + 1):
            attempts = attempt
            result = self._sandbox.run_tests(test_code=tests, skill_code=code)
            exit_code = int(result.get("exit_code", -1))
            stdout = str(result.get("stdout", ""))
            stderr = str(result.get("stderr", ""))

            if exit_code == 0:
                return TDDResult(
                    success=True,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    attempts=attempts,
                )

            if attempt < self._max_retries and self._llm is not None:
                # Retry with revised code
                revised = self._revise_code(code, stderr + stdin_to_error(stdout), spec_name=code)
                if revised:
                    code = revised

        return TDDResult(
            success=False,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            attempts=attempts,
        )

    def _run_local_tdd(self, code: str, tests: str) -> TDDResult:
        """Fallback: write temp files and run pytest locally."""
        import tempfile

        tmpdir = Path(tempfile.mkdtemp(prefix="skill_tdd_"))
        try:
            (tmpdir / "skill.py").write_text(code)
            (tmpdir / "test_skill.py").write_text(tests)

            proc = subprocess.run(
                ["python", "-m", "pytest", "-v"],
                cwd=str(tmpdir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            return TDDResult(
                success=proc.returncode == 0,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                attempts=1,
            )
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 6. Promote
    # ------------------------------------------------------------------

    def _promote(
        self,
        skill_name: str,
        code: str,
        metadata: dict | None = None,
        commit: bool = True,
    ) -> PromoteResult:
        """Write the skill file, hot-reload, register in DB, git-commit."""
        skill_path = safe_skill_path(self._skills_dir, skill_name)
        if skill_path is None:
            return PromoteResult(
                success=False,
                error=f"path traversal detected in skill name: {skill_name!r}",
            )
        try:
            skill_path.write_text(code)
        except OSError as exc:
            return PromoteResult(success=False, error=f"write failed: {exc}")

        # Hot-reload
        try:
            self._registry.get_tools()
        except Exception as exc:
            return PromoteResult(
                success=False,
                skill_path=str(skill_path),
                error=f"hot-reload failed: {exc}",
            )

        # DB registration
        meta = metadata or {}
        try:
            self._db.register_skill(
                name=skill_name,
                module=skill_name,
                function=meta.get("function", skill_name),
                description=meta.get("description", ""),
                signature=meta.get("signature", ""),
                version=meta.get("version", "1.0.0"),
                created_by=meta.get("created_by", ""),
                git_commit="",
            )
        except Exception as exc:
            return PromoteResult(
                success=False,
                skill_path=str(skill_path),
                error=f"db register failed: {exc}",
            )

        git_ok = False
        if commit:
            git_ok = self._git_commit(skill_path)

        return PromoteResult(
            success=True,
            skill_path=str(skill_path),
            git_committed=git_ok,
        )

    def _git_commit(self, skill_path: Path) -> bool:
        """Stage and commit the skill file."""
        try:
            subprocess.run(
                ["git", "add", str(skill_path)],
                check=False,
                capture_output=True,
                timeout=30,
            )
            proc = subprocess.run(
                ["git", "commit", "-m", f"feat: promote skill {skill_path.stem}"],
                check=False,
                capture_output=True,
                timeout=30,
            )
            return proc.returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_skill_name(self, request: str) -> str:
        """Convert natural language to snake_case skill name, filtering stopwords."""
        STOPWORDS = {"a", "an", "the", "to", "of", "in", "on", "for", "and", "or", "is", "at", "by"}
        text = request.lower().strip()
        text = text.replace("-", " ").replace("/", " ")
        text = re.sub(r"[^a-z0-9]+", " ", text)
        words = [w for w in text.split() if w and w not in STOPWORDS]
        return "_".join(words)

    def _llm_classify(self, user_request: str) -> dict[str, Any]:
        """Ask LLM to classify request into skill spec."""
        try:
            response = self._llm.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Extract a Python skill name, description, "
                     "signature, and test cases from this request. "
                     "Output ONLY valid JSON."},
                    {"role": "user", "content": user_request},
                ],
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            return {}

    def _heuristic_spec(self, user_request: str) -> dict[str, Any]:
        """Fallback: heuristic spec generation when LLM unavailable."""
        name = self._extract_skill_name(user_request)
        return {
            "name": name,
            "description": user_request,
            "signature": f"def {name}(*args, **kwargs):",
            "test_cases": [],
        }

    def _build_tdd_prompt(self, spec: SkillSpec) -> str:
        """Build TDD-first prompt for code generation."""
        return f"""
# TDD Skill Generation for '{spec.name}'

## Description
{spec.description}

## Signature
{spec.signature}

## Test Cases
{chr(10).join(f'  - {t}' for t in spec.test_cases) or '  (derive from signature)'.strip()}

## Instructions
Follow strict TDD:
1. RED   — Write failing tests FIRST
2. GREEN — Write minimal code to pass
3. REFACTOR — Improve code while tests stay green

Output the test code first in a ```python block, then the implementation in a separate ```python block.
The implementation MUST be a single function matching the signature.
The tests MUST import the function from the implementation module.
"""

    def _parse_code_and_tests(self, raw: str) -> tuple[str, str]:
        """Extract code blocks from LLM response."""
        blocks = re.findall(r"```python\n(.*?)```", raw, re.DOTALL)
        if len(blocks) >= 2:
            return blocks[1].strip(), blocks[0].strip()
        elif len(blocks) == 1:
            return blocks[0].strip(), ""
        return "", ""

    def _revise_code(self, code: str, error_trace: str, spec_name: str) -> str | None:
        """Ask LLM to revise code based on error trace."""
        if self._llm is None:
            return None
        try:
            response = self._llm.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a debugging expert. Fix the code."},
                    {"role": "user", "content": f"Fix this code:\n```python\n{code}\n```\nError:\n{error_trace}"},
                ],
            )
            content = response.choices[0].message.content
            blocks = re.findall(r"```python\n(.*?)```", content, re.DOTALL)
            return blocks[0].strip() if blocks else content.strip()
        except Exception:
            return None

    def _stub_code(self, spec: SkillSpec) -> str:
        """Generate stub implementation for testing."""
        return f'''"""Stub implementation for {spec.name}."""


def test_function():
    """Placeholder — real implementation should override this."""
    return None
'''

    def _stub_tests(self, spec: SkillSpec) -> str:
        """Generate stub tests for testing."""
        return f'''"""Tests for {spec.name}."""
from skill import test_function


def test_basic():
    assert test_function() is not None
'''


def stdin_to_error(stdout: str) -> str:
    """Extract error output from stdout for retry prompts."""
    return stdout
