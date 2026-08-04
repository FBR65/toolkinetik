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
