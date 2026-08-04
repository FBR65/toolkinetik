"""Tests that IntentEngine.available_tools does not reload (#10).

SPEC: docs/SPEC-25-improvements.md #10
Tier 2 — available_tools must read from registry.registered_tools
instead of triggering a full get_tools() reload on every analyze().
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from toolkinetik.intent import IntentEngine


def _make_registry(tools: dict | None = None) -> MagicMock:
    reg = MagicMock()
    reg.registered_tools = tools or {}
    return reg


class TestAvailableToolsNoReload:
    def test_reads_from_registered_tools_without_reload(self):
        reg = _make_registry({"foo_skill": lambda: None, "bar_skill": lambda: None})
        engine = IntentEngine(registry=reg, llm=MagicMock())
        with patch.object(engine, "_ask_llm", return_value={"intent": "chat"}):
            engine.analyze("hello")
        reg.get_tools.assert_not_called()

    def test_returns_tool_names(self):
        fn = MagicMock()
        fn.__name__ = "weather_skill"
        reg = _make_registry({"weather_skill": fn})
        engine = IntentEngine(registry=reg, llm=MagicMock())
        tools = engine.available_tools()
        assert "weather_skill" in tools

    def test_empty_registered_tools_triggers_reload(self):
        reg = _make_registry({})
        fn = MagicMock()
        fn.__name__ = "loaded_skill"
        reg.get_tools.return_value = [fn]
        # After reload, registered_tools is populated
        def _populate():
            reg.registered_tools = {"loaded_skill": fn}
            return [fn]
        reg.get_tools.side_effect = _populate
        engine = IntentEngine(registry=reg, llm=MagicMock())
        tools = engine.available_tools()
        assert "loaded_skill" in tools
        reg.get_tools.assert_called_once()

    def test_no_registry_returns_empty(self):
        engine = IntentEngine(registry=None, llm=MagicMock())
        assert engine.available_tools() == []

    def test_registry_exception_returns_empty(self):
        reg = MagicMock()
        reg.registered_tools = MagicMock(side_effect=RuntimeError("boom"))
        engine = IntentEngine(registry=reg, llm=MagicMock())
        # Must not raise
        assert engine.available_tools() == []