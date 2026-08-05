"""Tests for rate limiting (P1.3).

SPEC: docs/SPEC-production-readiness.md P1.3
Rate limits per API key for HTTP and WebSocket endpoints.
"""

from __future__ import annotations

import os

os.environ["AGNO_API_KEY"] = "test-key-12345"


from fastapi.testclient import TestClient

from toolkinetik.app import app

AUTH_HEADERS = {"X-API-Key": "test-key-12345"}


class TestHttpRateLimit:
    def test_repeated_requests_within_limit_succeed(self):
        """Requests within the rate limit succeed."""
        from toolkinetik.rate_limiter import reset_rate_limiter
        reset_rate_limiter()
        with TestClient(app) as client:
            # Default limit is high enough for a few requests
            for _ in range(3):
                response = client.get("/api/health")
                assert response.status_code == 200

    def test_exceeding_rate_limit_returns_429(self):
        """Exceeding the rate limit returns 429 Too Many Requests."""
        from toolkinetik.rate_limiter import reset_rate_limiter, set_rate_limit
        reset_rate_limiter()
        # Set a very low limit for testing
        set_rate_limit("test-key-12345", max_requests=2, window_seconds=60)
        with TestClient(app) as client:
            # First 2 requests succeed
            assert client.get("/api/skills", headers=AUTH_HEADERS).status_code == 200
            assert client.get("/api/skills", headers=AUTH_HEADERS).status_code == 200
            # 3rd request should be rate limited (429)
            response = client.get("/api/skills", headers=AUTH_HEADERS)
            assert response.status_code == 429

    def test_rate_limit_resets_after_window(self):
        """Rate limit resets after the time window expires."""
        from toolkinetik.rate_limiter import reset_rate_limiter, set_rate_limit
        reset_rate_limiter()
        # 1 second window
        set_rate_limit("test-key-12345", max_requests=1, window_seconds=1)
        with TestClient(app) as client:
            assert client.get("/api/skills", headers=AUTH_HEADERS).status_code == 200
            assert client.get("/api/skills", headers=AUTH_HEADERS).status_code == 429
            # Wait for window to expire
            import time
            time.sleep(1.1)
            assert client.get("/api/skills", headers=AUTH_HEADERS).status_code == 200