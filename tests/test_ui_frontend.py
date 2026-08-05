"""Tests for the updated NiceGUI chat frontend (TDD: RED phase)."""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock, patch


def _reload_ui():
    """Reload the ui module so we pick up fresh imports."""
    import nicegui  # noqa: F401
    return importlib.reload(importlib.import_module("toolkinetik.ui"))


class TestUiConstants:
    """UI constants."""

    def test_api_base_constant(self):
        mod = _reload_ui()
        assert isinstance(mod.API_BASE, str)
        assert mod.HEADERS["X-API-Key"]


class TestChatFrontend:
    """Chat frontend structure."""

    def test_ui_has_main_page(self):
        mod = _reload_ui()
        assert hasattr(mod, "main_page")
        assert callable(mod.main_page)

    def test_ui_has_send_message(self):
        mod = _reload_ui()
        assert hasattr(mod, "send_message")
        assert callable(mod.send_message)


class TestAgentStatusIndicator:
    """UI shows agent status (which skill is being used)."""

    def test_ui_has_agent_status_label(self):
        """A label for 'agent status' exists in the module."""
        mod = _reload_ui()
        # The module should have a constant or function for status
        assert hasattr(mod, "_agent_status_label") or hasattr(mod, "agent_status")


class TestRagIndicator:
    """UI shows RAG activation."""

    def test_ui_has_rag_indicator(self):
        """A function/variable for RAG status exists."""
        mod = _reload_ui()
        assert hasattr(mod, "_rag_status") or hasattr(mod, "rag_status")


class TestWebSocketIntegration:
    """send_message uses WebSocket."""

    @patch("websockets.connect")
    @patch("nicegui.ui")
    def test_send_message_sends_via_websocket(self, mock_nicegui_ui, mock_ws_connect):
        """send_message connects to WS and sends text."""
        mod = _reload_ui()

        chat_input = MagicMock()
        chat_input.value = "Hi"

        mock_session = AsyncMock()
        mock_ws_connect.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.recv = AsyncMock(return_value='{"type": "response", "content": "Hello"}')

        mock_container = MagicMock()
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            mod.send_message(chat_input, mock_container)
        )
        # chat_input.value was cleared during send
        assert chat_input.value == ""
        # WebSocket was called
        mock_ws_connect.assert_called_once()

    @patch("websockets.connect")
    @patch("nicegui.ui")
    def test_send_message_handles_status_update(self, mock_nicegui_ui, mock_ws_connect):
        """send_message handles status-type messages from the server."""
        mod = _reload_ui()
        mod.reset_status()

        chat_input = MagicMock()
        chat_input.value = "test"

        # Capture the status after the status message is processed
        captured_status = []
        original_set = mod.set_intent_phase

        def capture_phase(phase):
            original_set(phase)
            captured_status.append(mod._agent_status)

        mod.set_intent_phase = capture_phase

        mock_session = AsyncMock()
        mock_ws_connect.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        # First recv: status message, second recv: response
        mock_session.recv = AsyncMock(side_effect=[
            '{"type": "status", "phase": "create_skill", "message": "Creating..."}',
            '{"type": "response", "content": "Done"}',
        ])

        mock_container = MagicMock()
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            mod.send_message(chat_input, mock_container)
        )
        # The create_skill phase should have been set at some point
        assert any("Skill" in s or "Erstelle" in s for s in captured_status), \
            f"expected create_skill status in {captured_status}"

    @patch("websockets.connect")
    @patch("nicegui.ui")
    def test_send_message_handles_error_response(self, mock_nicegui_ui, mock_ws_connect):
        """send_message handles error-type messages from the server."""
        mod = _reload_ui()

        chat_input = MagicMock()
        chat_input.value = "test"

        mock_session = AsyncMock()
        mock_ws_connect.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.recv = AsyncMock(return_value='{"type": "error", "content": "LLM down"}')

        mock_container = MagicMock()
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            mod.send_message(chat_input, mock_container)
        )
        # After error, status should be reset
        assert mod._agent_status == "Bereit"

    @patch("websockets.connect")
    @patch("nicegui.ui")
    def test_send_message_empty_input_returns_early(self, mock_nicegui_ui, mock_ws_connect):
        """send_message with empty input returns without connecting."""
        mod = _reload_ui()

        chat_input = MagicMock()
        chat_input.value = ""

        mock_container = MagicMock()
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            mod.send_message(chat_input, mock_container)
        )
        mock_ws_connect.assert_not_called()
