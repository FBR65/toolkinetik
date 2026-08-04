"""Tests for the LLM-driven IntentEngine (TDD: RED phase)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from toolkinetik.coding_agent import SkillSpec
from toolkinetik.intent import IntentEngine


class TestIntentEngineBasic:
    """IntentEngine: basic LLM-driven detection."""

    def test_engine_returns_existing_skill(self):
        """Request matches an existing skill → returns SkillMatch(action='execute', skill_name='...')"""
        registry = MagicMock()
        registry.get_tools.return_value = []
        engine = IntentEngine(registry=registry, llm=MagicMock())
        with patch.object(engine, "_ask_llm") as mock_llm:
            mock_llm.return_value = {
                "intent": "execute_skill",
                "skill_name": "calculate_fibonacci",
            }
            result = engine.analyze("Berechne die 10. Fibonacci-Zahl")
            assert result.action == "execute_skill"
            assert result.skill_name == "calculate_fibonacci"

    def test_engine_returns_rag_needed(self):
        """Request mentions 'dokumente durchsuchen' → action='rag_search'"""
        registry = MagicMock()
        registry.get_tools.return_value = []
        engine = IntentEngine(registry=registry, llm=MagicMock())
        with patch.object(engine, "_ask_llm") as mock_llm:
            mock_llm.return_value = {
                "intent": "rag_search",
                "query": "Klimawandel in den Dokumenten",
            }
            result = engine.analyze("Suche nach 'Klimawandel' in unseren Dokumenten")
            assert result.action == "rag_search"
            assert "Klimawandel" in result.query

    def test_engine_returns_extension_needed(self):
        """Request for unknown capability → action='create_skill', returns SkillSpec"""
        registry = MagicMock()
        registry.get_tools.return_value = []
        engine = IntentEngine(registry=registry, llm=MagicMock())
        with patch.object(engine, "_ask_llm") as mock_llm:
            mock_llm.return_value = {
                "intent": "create_skill",
                "skill_name": "create_presentation",
                "description": "Erstelle eine Powerpoint-Präsentation",
                "signature": "def create_presentation(topic: str, n_slides: int = 3) -> str",
            }
            result = engine.analyze("Erstelle eine Powerpoint-Präsentation über KI")
            assert result.action == "create_skill"
            assert isinstance(result.skill_spec, SkillSpec)
            assert result.skill_spec.name == "create_presentation"

    def test_engine_falls_back_to_chat(self):
        """Request is a normal chat → action='chat'"""
        registry = MagicMock()
        registry.get_tools.return_value = []
        engine = IntentEngine(registry=registry, llm=MagicMock())
        with patch.object(engine, "_ask_llm") as mock_llm:
            mock_llm.return_value = {"intent": "chat"}
            result = engine.analyze("Erkläre mir Quantum Computing")
            assert result.action == "chat"

    def test_engine_lists_available_tools(self):
        """Engine exposes currently loaded tool names."""
        registry = MagicMock()
        fn = MagicMock()
        fn.__name__ = "calculate_fibonacci"
        registry.registered_tools = {"calculate_fibonacci": fn}
        engine = IntentEngine(registry=registry, llm=MagicMock())
        tools = engine.available_tools()
        assert "calculate_fibonacci" in tools
