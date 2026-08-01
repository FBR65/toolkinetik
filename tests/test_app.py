"""Tests for the FastAPI core engine (app.py).

AGNO_API_KEY is set as an env var *before* importing the app so that the
Settings singleton picks up a deterministic key for authentication tests.
"""

from __future__ import annotations

import os

# Set the API key BEFORE importing the app so Settings uses this value.
os.environ["AGNO_API_KEY"] = "test-key-12345"

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