"""Intent detection & autonomous skill-creation loop.

Task 5.1: IntentDetector compares user requests against the available
tool catalogue and, when no existing tool can satisfy the request, emits
a SkillSpec for the missing capability. SkillCreationOrchestrator wires
the detector together with CodingAgent, TDDLoop, and SkillPromoter to
close the create-test-promote loop autonomously.
"""

from __future__ import annotations

import re

from toolkinetik.coding_agent import CodingAgent, CodingResult, SkillSpec
from toolkinetik.promotion import SkillPromoter
from toolkinetik.registry import DynamicToolRegistry
from toolkinetik.sandbox import SandboxRunner
from toolkinetik.tdd_loop import TDDLoop

# ---------------------------------------------------------------------------
# IntentDetector
# ---------------------------------------------------------------------------


class IntentDetector:
    """Detect when a user request needs a skill that doesn't yet exist."""

    def __init__(self, registry: DynamicToolRegistry | None = None) -> None:
        self.registry = registry

    # -- public API ---------------------------------------------------------

    def detect_missing_skill(self, user_request: str) -> SkillSpec | None:
        """Return a SkillSpec if no existing tool matches, else None."""
        tool_names: list = []
        if self.registry is not None:
            try:
                tools = self.registry.get_tools()
                tool_names = [getattr(t, "__name__", str(t)) for t in tools]
            except Exception:
                tool_names = []

        # A match means an existing tool can handle the request.
        if self._match_tools(user_request, tool_names):
            return None

        skill_name = self._extract_skill_name(user_request)
        return SkillSpec(
            name=skill_name,
            description=f"Auto-generated skill for: {user_request}",
            signature=f"def {skill_name}(*args, **kwargs):",
            test_cases=[f"{skill_name} handles basic usage"],
        )

    # -- helpers ------------------------------------------------------------

    def _extract_skill_name(self, request: str) -> str:
        """Convert natural language request to a snake_case skill name.

        Examples:
          "PDF to markdown"     -> "pdf_to_markdown"
          "calculate fibonacci" -> "calculate_fibonacci"
        """
        # Lowercase and replace common separators with spaces.
        text = request.lower().strip()
        # Replace hyphens and slashes with spaces.
        text = text.replace("-", " ").replace("/", " ")
        # Collapse non-alphanumeric to spaces.
        text = re.sub(r"[^a-z0-9]+", " ", text)
        # Split into words, drop empties.
        words = [w for w in text.split() if w]
        # Join with underscores.
        return "_".join(words)

    def _match_tools(self, request: str, tool_names: list) -> bool:
        """Return True if any tool name keyword appears in the request."""
        request_lower = request.lower()
        for tool_name in tool_names:
            name = tool_name.lower()
            # Split the tool name into constituent keywords.
            parts = name.split("_")
            for part in parts:
                if len(part) >= 3 and part in request_lower:
                    return True
            # Also check the full name as a substring.
            if len(name) >= 3 and name in request_lower:
                return True
        return False


# ---------------------------------------------------------------------------
# SkillCreationOrchestrator
# ---------------------------------------------------------------------------


class SkillCreationOrchestrator:
    """Orchestrate the detect → create → test → promote loop."""

    def __init__(
        self,
        detector: IntentDetector,
        coding_agent: CodingAgent,
        sandbox: SandboxRunner,
        promoter: SkillPromoter,
        tdd_loop: TDDLoop,
    ) -> None:
        self.detector = detector
        self.coding_agent = coding_agent
        self.sandbox = sandbox
        self.promoter = promoter
        self.tdd_loop = tdd_loop

    def handle_request(self, user_request: str) -> str:
        """Process a user request through the full skill-creation loop.

        Returns a human-readable status message.
        """
        spec = self.detector.detect_missing_skill(user_request)
        if spec is None:
            return f"Skill already exists for request: {user_request}"

        # Generate code + tests.
        coding_result: CodingResult = self.coding_agent.create_skill(spec)
        if not coding_result.success:
            return (
                f"Skill creation failed for '{spec.name}': {coding_result.error}"
            )

        # Run TDD loop.
        tdd_result = self.tdd_loop.run(spec, coding_result.code, coding_result.tests)
        if not tdd_result.success:
            return (
                f"TDD loop failed for '{spec.name}': {tdd_result.error}"
            )

        # Promote the skill.
        promotion_result = self.promoter.promote(
            skill_name=spec.name,
            code=coding_result.code,
            metadata={"description": spec.description, "signature": spec.signature},
        )
        if not promotion_result.success:
            return (
                f"Promotion failed for '{spec.name}': {promotion_result.error}"
            )

        return (
            f"Skill '{spec.name}' created, tested, and promoted successfully "
            f"(git_committed={promotion_result.git_committed})"
        )