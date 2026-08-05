"""Shared test fixtures for ToolKinetik tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the rate limiter before each test to prevent cross-test contamination."""
    try:
        from toolkinetik.rate_limiter import reset_rate_limiter
        reset_rate_limiter()
    except ImportError:
        pass
    yield
    try:
        from toolkinetik.rate_limiter import reset_rate_limiter
        reset_rate_limiter()
    except ImportError:
        pass