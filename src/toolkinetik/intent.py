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
import time
from dataclasses import dataclass, field
from typing import Any

from toolkinetik.coding_agent import SkillSpec
from toolkinetik.registry import DynamicToolRegistry

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

    _VALID_INTENTS = frozenset({"execute_skill", "create_skill", "rag_search", "chat"})

    def __init__(self, registry: DynamicToolRegistry | None = None, llm: Any = None) -> None:
        self.registry = registry
        self._llm = llm
        self._cache: dict[str, dict[str, Any]] = {}  # request → intent_data
        self._cache_ttl = 300  # 5 minutes

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

    def available_tools_with_descriptions(self) -> list[tuple[str, str]]:
        """Return (name, description) pairs for currently loaded skills.

        Uses registered_skill_descriptions for SKILL.md-based skills and
        __doc__ for legacy Python skills. Falls back to empty description.
        """
        result: list[tuple[str, str]] = []
        if self.registry is None:
            return result
        try:
            tools = self.registry.registered_tools
            if not tools:
                tools_list = self.registry.get_tools()
                for t in tools_list:
                    name = getattr(t, "__name__", str(t))
                    desc = getattr(t, "__doc__", "") or ""
                    result.append((name, desc))
            else:
                descriptions = getattr(self.registry, "registered_skill_descriptions", {})
                for t in tools.values():
                    name = getattr(t, "__name__", str(t))
                    desc = descriptions.get(name, getattr(t, "__doc__", "") or "")
                    result.append((name, desc))
        except Exception:
            result = []
        return result

    def analyze(self, user_request: str) -> SkillMatch:
        """Classify *user_request* and return a :class:`SkillMatch`."""
        tool_names = self.available_tools()
        tool_descs = self.available_tools_with_descriptions()

        # Check cache (P2.2) — same request within TTL reuses result
        cache_key = user_request
        cached = self._cache.get(cache_key)
        if cached and time.monotonic() - cached.get("_ts", 0) < self._cache_ttl:
            intent_data = cached
        else:
            intent_data = self._ask_llm(user_request, tool_names, tool_descs)
            intent_data["_ts"] = time.monotonic()
            self._cache[cache_key] = intent_data

        intent = intent_data.get("intent", "chat")

        if intent not in self._VALID_INTENTS:
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

    def _ask_llm(self, user_request: str, tool_names: list[str], tool_descs: list[tuple[str, str]] | None = None) -> dict[str, Any]:
        """Call the LLM to classify the request.

        In production this sends the request + tool list to the OpenAI-compatible
        LLM endpoint and parses the JSON response.  In tests this is patched.
        """
        if self._llm is None:
            return {"intent": "chat"}
        prompt = self._build_prompt(user_request, tool_names, tool_descs)
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

    def _build_prompt(self, user_request: str, tool_names: list[str], tool_descs: list[tuple[str, str]] | None = None) -> str:
        """Build the LLM classification prompt.

        When tool_descs is available, includes skill descriptions for better
        classification. Otherwise falls back to tool names only.
        """
        if tool_descs:
            tools_str = "\n".join(
                f"  - {name}: {desc}" if desc else f"  - {name}"
                for name, desc in tool_descs
            ) or "  (none)"
        else:
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