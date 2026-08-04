"""Tests for intent-aware UI flow (TDD: RED phase).

Verifies that the frontend:
1. Sends messages via WebSocket (already tested in test_ui_frontend.py)
2. Displays agent status updates during intent processing
3. Shows wigolo research, code generation, and promotion phases
4. Falls back to chat for unclassifiable requests
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


def _reload_ui():
    """Reload ui module for fresh imports."""
    import importlib
    import nicegui  # noqa: F401
    return importlib.reload(importlib.import_module("toolkinetik.ui"))


class TestUiStatusUpdates:
    """Frontend displays agent status during intent processing."""

    def test_ui_has_set_agent_status_function(self):
        """A setter function exists to update agent status from WebSocket messages."""
        mod = _reload_ui()
        assert hasattr(mod, "set_agent_status")
        assert callable(mod.set_agent_status)

    def test_ui_has_set_rag_status_function(self):
        """A setter exists for RAG status."""
        mod = _reload_ui()
        assert hasattr(mod, "set_rag_status")
        assert callable(mod.set_rag_status)


class TestUiIntentPhaseTracking:
    """UI tracks intent phases (research, generate, test, promote)."""

    def test_ui_has_set_intent_phase_function(self):
        """A setter exists for intent phase tracking."""
        mod = _reload_ui()
        assert hasattr(mod, "set_intent_phase")
        assert callable(mod.set_intent_phase)

    def test_ui_intent_phase_updates_status(self):
        """Calling set_intent_phase updates the display."""
        mod = _reload_ui()
        mod.set_intent_phase("research")
        # The internal state should be updated
        assert mod._agent_status == "Suche..." or mod._agent_status != "Bereit"


class TestUiWebSocketMessageHandling:
    """WebSocket handler parses intent-phase messages."""

    def test_ui_has_websocket_send_message(self):
        """send_message function exists and is callable."""
        mod = _reload_ui()
        assert hasattr(mod, "send_message")
        assert callable(mod.send_message)

    def test_ui_reload_skills_function_exists(self):
        """reload_skills function exists."""
        mod = _reload_ui()
        assert hasattr(mod, "reload_skills")
        assert callable(mod.reload_skills)


class TestUiChatFallback:
    """Chat requests that need no skill show a different status."""

    def test_ui_sets_chat_status_for_normal_conversation(self):
        """set_intent_phase('chat') updates status to 'Bereit'."""
        mod = _reload_ui()
        mod.set_intent_phase("chat")
        assert mod._agent_status == "Bereit"

    def test_ui_sets_skill_creation_status(self):
        """set_intent_phase('create_skill') shows creation status."""
        mod = _reload_ui()
        mod.set_intent_phase("create_skill")
        assert "Erstelle" in mod._agent_status or "Skill" in mod._agent_status

    def test_ui_sets_rag_search_status(self):
        """set_intent_phase('rag_search') shows RAG status."""
        mod = _reload_ui()
        mod.set_intent_phase("rag_search")
        assert mod._rag_status == "Aktiv"


class TestUiClearStatus:
    """UI resets status after response."""

    def test_clear_status_after_response(self):
        """reset_status() returns to default."""
        mod = _reload_ui()
        mod._agent_status = "Erstelle Skill..."
        mod._rag_status = "Aktiv"
        mod.reset_status()
        assert mod._agent_status == "Bereit"
        assert mod._rag_status == "Aus"
