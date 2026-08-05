"""In-memory rate limiter for ToolKinetik API endpoints (P1.3).

Lightweight per-API-key rate limiting without external dependencies.
Uses a sliding window counter per API key.
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse

# Default rate limits (configurable via ENV).
_DEFAULT_HTTP_LIMIT = 60  # requests per minute
_DEFAULT_WS_LIMIT = 20  # messages per minute

# In-memory state: {api_key: [(timestamp, ...)]}
_request_log: dict[str, list[float]] = defaultdict(list)
_rate_limits: dict[str, tuple[int, int]] = {}  # {api_key: (max_requests, window_seconds)}
_lock = Lock()


def reset_rate_limiter() -> None:
    """Clear all rate limiter state (for tests)."""
    with _lock:
        _request_log.clear()
        _rate_limits.clear()


def set_rate_limit(api_key: str, max_requests: int, window_seconds: int) -> None:
    """Set a custom rate limit for a specific API key (for tests)."""
    with _lock:
        _rate_limits[api_key] = (max_requests, window_seconds)


def _get_limit(api_key: str) -> tuple[int, int]:
    """Return (max_requests, window_seconds) for the given key."""
    if api_key in _rate_limits:
        return _rate_limits[api_key]
    return (_DEFAULT_HTTP_LIMIT, 60)


def check_rate_limit(api_key: str) -> bool:
    """Check if a request is within the rate limit.

    Returns True if allowed, False if rate-limited.
    """
    now = time.monotonic()
    max_requests, window_s = _get_limit(api_key)

    with _lock:
        log = _request_log[api_key]
        # Remove timestamps outside the window
        cutoff = now - window_s
        while log and log[0] < cutoff:
            log.pop(0)

        if len(log) >= max_requests:
            return False

        log.append(now)
        return True


async def rate_limit_middleware(request: Request, call_next: Any) -> Response:
    """FastAPI middleware that enforces rate limits on authenticated endpoints.

    Health endpoints (/api/health, /api/health/deep) are not rate-limited.
    """
    # Skip rate limiting for health checks
    path = request.url.path
    if path in ("/api/health", "/api/health/deep", "/"):
        return await call_next(request)

    # Extract API key from header or query param
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        # Let auth middleware handle it
        return await call_next(request)

    if not check_rate_limit(api_key):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
        )

    return await call_next(request)