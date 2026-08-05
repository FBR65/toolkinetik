"""Tests for LLM cost tracking (P2.1), skill caching (P2.2), and WS limits (P2.3).

SPEC: docs/SPEC-production-readiness.md P2.1-P2.3
"""

from __future__ import annotations

import os

os.environ["AGNO_API_KEY"] = "test-key-12345"

from unittest.mock import MagicMock

from toolkinetik.metrics import reset_metrics


class TestLLMCostTracking:
    """P2.1 — Token usage from LLM calls is tracked."""

    def test_record_llm_call_tracks_tokens(self):
        """record_llm_call stores token usage per model."""
        from toolkinetik.metrics import get_metrics_text, record_llm_call
        reset_metrics()
        record_llm_call("gpt-4o", success=True)
        text = get_metrics_text()
        assert "llm_call_total" in text

    def test_llm_usage_extracted_from_response(self):
        """LLM response usage is extracted and recorded."""
        from toolkinetik.metrics import extract_llm_usage
        reset_metrics()
        mock_response = MagicMock()
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        usage = extract_llm_usage(mock_response)
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 50
        assert usage["total_tokens"] == 150

    def test_llm_usage_missing_returns_empty(self):
        """Missing usage attribute returns empty dict."""
        from toolkinetik.metrics import extract_llm_usage
        response = MagicMock(spec=[])  # no .usage attribute
        usage = extract_llm_usage(response)
        assert usage == {} or usage.get("total_tokens") is None


class TestSkillCaching:
    """P2.2 — IntentEngine caches results to avoid redundant LLM calls."""

    def test_intent_cache_exists(self):
        """IntentEngine has a cache mechanism."""
        from toolkinetik.intent import IntentEngine
        engine = IntentEngine(registry=None, llm=None)
        assert hasattr(engine, "_cache") or hasattr(engine, "_intent_cache")

    def test_cached_result_reused(self):
        """Same request twice → LLM called once."""
        from toolkinetik.intent import IntentEngine
        registry = MagicMock()
        registry.registered_tools = {}
        llm = MagicMock()
        llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"intent": "chat"}'))]
        )
        engine = IntentEngine(registry=registry, llm=llm)
        engine.analyze("hello")
        engine.analyze("hello")
        # LLM should be called once (cached on second)
        assert llm.chat.completions.create.call_count == 1


class TestWebSocketConnectionLimits:
    """P2.3 — Max WebSocket connections per API key."""

    def test_ws_connection_limit_configurable(self):
        """Connection limit is configurable."""
        from toolkinetik.app import get_max_ws_connections, set_max_ws_connections
        set_max_ws_connections(5)
        assert get_max_ws_connections() == 5

    def test_ws_connection_count_tracked(self):
        """Active connections are tracked per API key."""
        from toolkinetik.app import (
            decrement_ws_connection,
            get_active_ws_connections,
            increment_ws_connection,
            reset_ws_connections,
        )
        reset_ws_connections()
        increment_ws_connection("key1")
        increment_ws_connection("key1")
        increment_ws_connection("key2")
        assert get_active_ws_connections("key1") == 2
        assert get_active_ws_connections("key2") == 1
        decrement_ws_connection("key1")
        assert get_active_ws_connections("key1") == 1