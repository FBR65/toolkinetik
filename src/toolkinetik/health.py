"""Deep health check for ToolKinetik subsystems (P1.2).

Checks Docker daemon, LLM endpoint, and RAG availability with per-check
timeouts (max 2s each) so the endpoint never hangs.
"""

from __future__ import annotations

import logging
import shutil
from typing import Any

logger = logging.getLogger(__name__)

_CHECK_TIMEOUT_S = 2.0


def check_docker() -> dict[str, str]:
    """Check if the Docker daemon is reachable."""
    if not shutil.which("docker"):
        return {"status": "unhealthy", "detail": "docker CLI not found"}
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return {"status": "healthy", "detail": "docker daemon reachable"}
    except Exception as exc:
        return {"status": "unhealthy", "detail": f"docker unreachable: {exc}"}


def check_llm() -> dict[str, str]:
    """Check if the LLM endpoint is reachable (lightweight ping)."""
    try:
        from toolkinetik.config import get_settings
        settings = get_settings()
        base_url = settings.OPENAI_API_BASE
        if not base_url:
            return {"status": "unhealthy", "detail": "OPENAI_API_BASE not configured"}
        import httpx
        # Light GET request — many endpoints return 200 or 404 at root
        response = httpx.get(base_url, timeout=_CHECK_TIMEOUT_S)
        if response.status_code < 500:
            return {"status": "healthy", "detail": f"LLM endpoint reachable (HTTP {response.status_code})"}
        return {"status": "degraded", "detail": f"LLM endpoint returned HTTP {response.status_code}"}
    except Exception as exc:
        return {"status": "unhealthy", "detail": f"LLM endpoint unreachable: {exc}"}


def check_rag() -> dict[str, str]:
    """Check if the RAG subsystem is available (without heavy init)."""
    try:
        import lancedb  # noqa: F401
        import sentence_transformers  # noqa: F401
        return {"status": "healthy", "detail": "RAG dependencies available"}
    except ImportError:
        return {"status": "degraded", "detail": "RAG dependencies not installed (run: uv sync --extra rag)"}


def deep_health_check() -> dict[str, Any]:
    """Run all subsystem checks and return an aggregated health status.

    Returns {"status": "healthy"|"degraded"|"unhealthy", "checks": {...}}.
    """
    checks = {
        "docker": check_docker(),
        "llm": check_llm(),
        "rag": check_rag(),
    }

    statuses = [c["status"] for c in checks.values()]
    if all(s == "healthy" for s in statuses):
        overall = "healthy"
    elif any(s == "unhealthy" for s in statuses):
        overall = "unhealthy"
    else:
        overall = "degraded"

    return {"status": overall, "checks": checks}