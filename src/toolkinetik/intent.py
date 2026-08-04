"""Intent detection & autonomous skill-creation loop.

Task 5.1: IntentDetector compares user requests against the available
tool catalogue and, when no existing tool can satisfy the request, emits
a SkillSpec for the missing capability. SkillCreationOrchestrator wires
the detector together with CodingAgent, TDDLoop, and SkillPromoter to
close the create-test-promote loop autonomously.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from toolkinetik.coding_agent import CodingAgent, CodingResult, SkillSpec
from toolkinetik.promotion import SkillPromoter
from toolkinetik.registry import DynamicToolRegistry
from toolkinetik.sandbox import SandboxRunner
from toolkinetik.tdd_loop import TDDLoop

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IntentEngine (LLM-driven)
# ---------------------------------------------------------------------------


@dataclass
class SkillMatch:
    """Result of IntentEngine.analyze."""

    action: str  # "execute_skill" | "create_skill" | "rag_search" | "chat"
    skill_name: str = ""
    skill_spec: SkillSpec | None = None
    query: str = ""
    tool_names: list[str] = field(default_factory=list)


class IntentEngine:
    """LLM-driven intent detector.

    Unlike IntentDetector (keyword-based), this engine asks an LLM to classify
    a user request into one of four intents:
    - execute_skill: an existing skill can handle the request
    - create_skill:  a new skill must be generated (TDD loop)
    - rag_search:    the request needs document search (RAG)
    - chat:          normal conversation, no skill needed
    """

    def __init__(self, registry: DynamicToolRegistry | None = None, llm: Any = None) -> None:
        self.registry = registry
        self._llm = llm

    def available_tools(self) -> list[str]:
        """Return names of currently loaded skills without triggering a reload."""
        names: list[str] = []
        if self.registry is None:
            return names
        try:
            tools = self.registry.registered_tools
            if not tools:
                # Cold-start: no tools registered yet, do a one-shot load.
                tools_list = self.registry.get_tools()
                names = [getattr(t, "__name__", str(t)) for t in tools_list]
            else:
                names = [getattr(t, "__name__", str(t)) for t in tools.values()]
        except Exception:
            names = []
        return names

    def analyze(self, user_request: str) -> SkillMatch:
        """Classify *user_request* and return a :class:`SkillMatch`."""
        tool_names = self.available_tools()
        intent_data = self._ask_llm(user_request, tool_names)
        intent = intent_data.get("intent", "chat")

        valid_intents = {"execute_skill", "create_skill", "rag_search", "chat"}
        if intent not in valid_intents:
            logger.warning("LLM returned unknown intent %r; degrading to chat", intent)
            intent = "chat"

        if intent == "execute_skill":
            return SkillMatch(
                action="execute_skill",
                skill_name=intent_data.get("skill_name", ""),
                tool_names=tool_names,
            )
        if intent == "create_skill":
            spec = SkillSpec(
                name=intent_data.get("skill_name", ""),
                description=intent_data.get("description", ""),
                signature=intent_data.get("signature", ""),
                test_cases=[],
            )
            return SkillMatch(
                action="create_skill",
                skill_spec=spec,
                tool_names=tool_names,
            )
        if intent == "rag_search":
            return SkillMatch(
                action="rag_search",
                query=intent_data.get("query", ""),
                tool_names=tool_names,
            )
        return SkillMatch(action="chat", tool_names=tool_names)

    def _ask_llm(self, user_request: str, tool_names: list[str]) -> dict[str, Any]:
        """Call the LLM to classify the request.

        In production this sends the request + tool list to the OpenAI-compatible
        LLM endpoint and parses the JSON response.  In tests this is patched.
        """
        if self._llm is None:
            return {"intent": "chat"}
        prompt = self._build_prompt(user_request, tool_names)
        from toolkinetik.config import get_settings
        try:
            response = self._llm.chat.completions.create(
                model=get_settings().OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                timeout=get_settings().LLM_TIMEOUT,
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            logger.exception("LLM classify failed; degrading to chat intent")
            return {"intent": "chat"}

    def _build_prompt(self, user_request: str, tool_names: list[str]) -> str:
        """Build the LLM classification prompt."""
        tools_str = "\n".join(f"  - {t}" for t in tool_names) or "  (none)"
        return f"""
You are an intent classifier for a self-extending agent system called ToolKinetik.

Available tools/skills:
{tools_str}

Classify the following user request into EXACTLY ONE of these intents:
- "execute_skill": An existing tool can fulfill this request. Return the exact tool name in 'skill_name'.
- "create_skill": No existing tool can handle this. Return 'skill_name', 'description', and 'signature' for a new Python function.
- "rag_search": The user wants to search documents/documents/files. Return the search query in 'query'.
- "chat": Normal conversation, no skill needed.

User request: "{user_request}"

Output ONLY valid JSON:
"""


# ---------------------------------------------------------------------------
# IntentDetector (legacy — keyword-based, kept for backward compatibility)
# ---------------------------------------------------------------------------


class IntentDetector:
    """Detect when a user request needs a skill that doesn't yet exist."""

    def __init__(self, registry: DynamicToolRegistry | None = None) -> None:
        self.registry = registry

    # -- public API ---------------------------------------------------------

    def detect_missing_skill(self, user_request: str) -> SkillSpec | None:
        """Return a SkillSpec if no existing tool matches, else None."""
        tool_names: list[str] = []
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

    def _match_tools(self, request: str, tool_names: list[str]) -> bool:
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