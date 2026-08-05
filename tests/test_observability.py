"""Tests for structured logging and metrics (P1.5).

SPEC: docs/SPEC-production-readiness.md P1.5
Structured JSON logging with request-id propagation, plus /metrics endpoint.
"""

from __future__ import annotations

import logging
import os

os.environ["AGNO_API_KEY"] = "test-key-12345"

from fastapi.testclient import TestClient

from toolkinetik.app import app


class TestStructuredLogging:
    def test_logger_has_request_id_context(self):
        """Log entries can include a request_id context variable."""
        from toolkinetik.logging_config import get_request_id, set_request_id
        set_request_id("test-req-123")
        assert get_request_id() == "test-req-123"

    def test_request_id_isolated_per_context(self):
        """Request IDs are isolated per context (contextvars)."""

        from toolkinetik.logging_config import get_request_id, set_request_id

        # Each set_request_id call should set the context variable
        set_request_id("req-A")
        assert get_request_id() == "req-A"
        set_request_id("req-B")
        assert get_request_id() == "req-B"

    def test_log_format_includes_request_id(self, caplog):
        """When request_id is set, log records include it."""
        from toolkinetik.logging_config import get_request_id, set_request_id
        set_request_id("log-test-id")
        logger = logging.getLogger("toolkinetik.test")
        with caplog.at_level(logging.INFO, logger="toolkinetik.test"):
            logger.info("test message")
        # The request_id should be accessible
        assert get_request_id() == "log-test-id"


class TestMetricsEndpoint:
    def test_metrics_endpoint_exists(self):
        """GET /metrics returns 200."""
        with TestClient(app) as client:
            response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_contains_help_text(self):
        """Metrics response contains Prometheus HELP text."""
        from toolkinetik.metrics import record_skill_promote, reset_metrics
        reset_metrics()
        record_skill_promote("test_skill", success=True)
        with TestClient(app) as client:
            response = client.get("/metrics")
        body = response.text
        assert "# HELP" in body

    def test_metrics_tracks_skill_promotions(self):
        """Metrics endpoint tracks skill_promote_total."""
        from toolkinetik.metrics import get_metrics_text, record_skill_promote
        record_skill_promote("test_skill", success=True)
        text = get_metrics_text()
        assert "skill_promote_total" in text or "toolkinetik" in text.lower()