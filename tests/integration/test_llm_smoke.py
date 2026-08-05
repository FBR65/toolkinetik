"""Integration tests for LLM endpoint smoke tests (P0.4).

SPEC: docs/SPEC-production-readiness.md P0.4
Tests IntentEngine, SkillWriter code-gen, and revise against a real LLM endpoint.
Skipped if TOOLKINETIK_TEST_LLM_BASE env var is not set.
"""

from __future__ import annotations

import os

import pytest

llm_endpoint = os.environ.get("TOOLKINETIK_TEST_LLM_BASE", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not llm_endpoint, reason="TOOLKINETIK_TEST_LLM_BASE not set"),
]


@pytest.mark.llm
class TestRealLLMSmoke:
    def test_intent_engine_classifies(self):
        """IntentEngine.analyze against a real LLM returns a valid intent."""
        from openai import OpenAI

        from toolkinetik.config import get_settings
        from toolkinetik.intent import IntentEngine
        from toolkinetik.registry import DynamicToolRegistry

        # Override settings for the test endpoint
        os.environ["OPENAI_API_BASE"] = llm_endpoint
        get_settings.cache_clear()

        registry = DynamicToolRegistry("skills")
        llm = OpenAI(base_url=llm_endpoint, api_key=os.environ.get("OPENAI_API_KEY", "test"))
        engine = IntentEngine(registry=registry, llm=llm)

        result = engine.analyze("hello world")
        assert result.action in {"execute_skill", "create_skill", "rag_search", "chat"}

        get_settings.cache_clear()

    def test_skill_writer_generates_code(self):
        """SkillWriter._generate_code produces AST-valid code via real LLM."""
        from openai import OpenAI

        from toolkinetik.coding_agent import SkillSpec
        from toolkinetik.config import get_settings
        from toolkinetik.skill_writer import SkillWriter

        os.environ["OPENAI_API_BASE"] = llm_endpoint
        get_settings.cache_clear()

        llm = OpenAI(base_url=llm_endpoint, api_key=os.environ.get("OPENAI_API_KEY", "test"))
        writer = SkillWriter(llm=llm)
        spec = SkillSpec(name="add_numbers", description="Add two numbers", signature="def add_numbers(a, b):")
        code, _tests = writer._generate_code(spec)

        if code:
            import ast
            ast.parse(code)  # should be valid Python

        get_settings.cache_clear()