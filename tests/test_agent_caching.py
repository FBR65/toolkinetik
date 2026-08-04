"""Tests that create_agent is cached and invalidated on reload (#9).

SPEC: docs/SPEC-25-improvements.md #9
Tier 2 — create_agent must not be called per WebSocket message.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("AGNO_API_KEY", "test-key-12345")

import pytest


@pytest.fixture
def reset_agent_cache():
    import toolkinetik.app as app_mod
    app_mod._agent = None
    yield app_mod
    app_mod._agent = None


class TestAgentCaching:
    def test_agent_cached_across_calls(self, reset_agent_cache):
        from toolkinetik.app import get_agent
        with patch("toolkinetik.app.create_agent", return_value=MagicMock(name="agent")) as mock_create:
            a1 = get_agent()
            a2 = get_agent()
        assert a1 is a2
        assert mock_create.call_count == 1

    def test_reload_invalidates_cache(self, reset_agent_cache):
        from toolkinetik.app import get_agent, invalidate_agent_cache
        with patch("toolkinetik.app.create_agent", return_value=MagicMock()) as mock_create:
            get_agent()
            invalidate_agent_cache()
            get_agent()
        assert mock_create.call_count == 2

    def test_reload_skills_endpoint_invalidates(self, reset_agent_cache):
        from fastapi.testclient import TestClient

        from toolkinetik.app import app
        with patch("toolkinetik.app.create_agent", return_value=MagicMock()), \
             patch("toolkinetik.app.registry") as mock_reg:
            mock_reg.get_tools.return_value = []
            with TestClient(app) as client:
                client.post("/api/reload-skills", headers={"X-API-Key": "test-key-12345"})
            # Agent cache should now be None (invalidated by endpoint)
            import toolkinetik.app as app_mod
            assert app_mod._agent is None