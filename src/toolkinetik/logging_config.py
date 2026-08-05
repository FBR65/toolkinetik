"""Structured logging configuration with request-id propagation (P1.5).

Uses contextvars to propagate a request_id through all log entries within
a single request/session, enabling correlation across log lines.
"""

from __future__ import annotations

import contextvars
import logging
import sys

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request_id (empty string if not set)."""
    return _request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the request_id for the current context."""
    _request_id_var.set(request_id)


def reset_request_id() -> None:
    """Clear the request_id for the current context."""
    _request_id_var.set("")


class RequestIdFilter(logging.Filter):
    """Logging filter that adds request_id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging with request_id.

    Call this once at application startup.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.addFilter(RequestIdFilter())
    formatter = logging.Formatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", '
        '"request_id": "%(request_id)s", "message": "%(message)s"}'
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(handler)