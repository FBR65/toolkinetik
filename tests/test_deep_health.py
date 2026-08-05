"""Tests for deep health check endpoint (P1.2).

SPEC: docs/SPEC-production-readiness.md P1.2
/api/health/deep checks Docker daemon, LLM endpoint, and RAG availability.
"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

os.environ["AGNO_API_KEY"] = "test-key-12345"

from toolkinetik.app import app

AUTH_HEADERS = {"X-API-Key": "test-key-12345"}


class TestDeepHealth:
    def test_deep_health_endpoint_exists(self):
        """GET /api/health/deep returns 200."""
        with TestClient(app) as client:
            response = client.get("/api/health/deep")
        assert response.status_code == 200

    def test_deep_health_returns_status(self):
        """Response contains overall status."""
        with TestClient(app) as client:
            response = client.get("/api/health/deep")
        data = response.json()
        assert "status" in data
        assert data["status"] in {"healthy", "degraded", "unhealthy"}

    def test_deep_health_has_checks_dict(self):
        """Response contains individual check results."""
        with TestClient(app) as client:
            response = client.get("/api/health/deep")
        data = response.json()
        assert "checks" in data
        assert isinstance(data["checks"], dict)

    def test_deep_health_checks_docker(self):
        """Response includes a Docker check."""
        with TestClient(app) as client:
            response = client.get("/api/health/deep")
        data = response.json()
        assert "docker" in data["checks"]

    def test_deep_health_checks_llm(self):
        """Response includes an LLM check."""
        with TestClient(app) as client:
            response = client.get("/api/health/deep")
        data = response.json()
        assert "llm" in data["checks"]

    def test_deep_health_checks_rag(self):
        """Response includes a RAG check."""
        with TestClient(app) as client:
            response = client.get("/api/health/deep")
        data = response.json()
        assert "rag" in data["checks"]

    def test_deep_health_no_auth_required(self):
        """Deep health does not require auth (like /api/health)."""
        with TestClient(app) as client:
            response = client.get("/api/health/deep")
        assert response.status_code == 200  # not 403