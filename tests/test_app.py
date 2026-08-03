"""Tests for the FastAPI core engine (app.py).

AGNO_API_KEY is set as an env var *before* importing the app so that the
Settings singleton picks up a deterministic key for authentication tests.
"""

from __future__ import annotations

import os

# Set the API key BEFORE importing the app so Settings uses this value.
os.environ["AGNO_API_KEY"] = "test-key-12345"

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from toolkinetik.app import app

AUTH_HEADERS = {"X-API-Key": "test-key-12345"}


def test_health_endpoint() -> None:
    """GET /api/health returns 200 without auth."""
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_reload_skills_without_key() -> None:
    """POST /api/reload-skills without X-API-Key returns 403."""
    with TestClient(app) as client:
        response = client.post("/api/reload-skills")
    assert response.status_code == 403


def test_reload_skills_with_key() -> None:
    """POST /api/reload-skills with correct key returns 200."""
    with TestClient(app) as client:
        response = client.post("/api/reload-skills", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_list_skills_without_key() -> None:
    """GET /api/skills without X-API-Key returns 403."""
    with TestClient(app) as client:
        response = client.get("/api/skills")
    assert response.status_code == 403


def test_list_skills_with_key() -> None:
    """GET /api/skills with correct key returns 200."""
    with TestClient(app) as client:
        response = client.get("/api/skills", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert isinstance(data["tools"], list)


def test_reload_skills_returns_tool_list() -> None:
    """POST /api/reload-skills response contains a loaded_tools list."""
    with TestClient(app) as client:
        response = client.post("/api/reload-skills", headers=AUTH_HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert "loaded_tools" in data
    assert isinstance(data["loaded_tools"], list)


def test_api_key_uses_constant_time_compare() -> None:
    """API-key verification must use a timing-safe comparison (B2)."""
    from toolkinetik.app import verify_api_key
    from fastapi import HTTPException

    with patch("toolkinetik.app.secrets.compare_digest", wraps=__import__("secrets").compare_digest) as mock:
        with pytest.raises(HTTPException) as excinfo:
            verify_api_key("wrong-key")
        assert excinfo.value.status_code == 403
    assert mock.called


def test_api_key_correct_value_accepted() -> None:
    """Correct API key must still authenticate (regression)."""
    from toolkinetik.app import verify_api_key

    assert verify_api_key("test-key-12345") == "test-key-12345"


def test_websocket_rejects_invalid_key() -> None:
    """WebSocket chat with an invalid api_key must close (policy violation)."""
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/chat?api_key=wrong-key"):
                pass
        assert excinfo.value.code == 1008


def test_websocket_accepts_valid_key() -> None:
    """WebSocket chat with a valid api_key must connect and reply."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/chat?api_key=test-key-12345") as ws:
            ws.send_text("hello")
            received = ws.receive_json()
            assert isinstance(received, dict)
            assert "content" in received


def test_create_agent_uses_openaichat_model() -> None:
    """create_agent must build the LLM via OpenAIChat (agno >= 2 API).

    Regression test: Agent(api_key=..., base_url=...) is no longer valid in
    agno 2.x and raised a TypeError; the endpoint config now lives on the
    model instance.
    """
    from toolkinetik.app import create_agent
    from toolkinetik.config import get_settings
    from toolkinetik.registry import DynamicToolRegistry

    settings = get_settings()
    agent = create_agent()

    assert agent.model.id == settings.OPENAI_MODEL
    assert agent.model.base_url == settings.OPENAI_API_BASE
    assert agent.model.api_key == (settings.OPENAI_API_KEY or None)
    assert agent.tools
    expected = {t.__name__ for t in DynamicToolRegistry(settings.SKILLS_DIR).get_tools()}
    assert {t.__name__ for t in agent.tools} == expected