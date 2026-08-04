"""MCP integration for wigolo (@KnockOutEZ/wigolo) — Agno-Tool-Paket.

wigolo is a self-hosted coding-agent search MCP server (PyPi, GitHub, docs,
code example search).  This module wraps wigolo as an Agno-compatible
toolkit (callable tools) so the master agent can use wigolo's
`research`, `fetch`, `crawl`, `extract`, `cache`, `find-similar`,
`research` tools without requiring the `mcp` Python SDK (which conflicts
with agno 2.8.x).

The wigolo server is launched on-demand via ``uvx @KnockOutEZ/wigolo``
and communicated with via a lightweight JSON-RPC protocol.  If the server
cannot be started (e.g. not installed, network issues), the toolkit
gracefully degrades to a local fallback that returns structured empty
results — the agent can still operate, just without wigolo research data.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)


class _StubClient:
    """Fallback client used when wigolo server is unavailable."""

    def research(self, query: str, context: str = "") -> dict:
        return {"query": query, "results": [], "error": "wigolo server unavailable"}

    def extract(self, url: str) -> str:
        return ""


class _WigoloClient:
    """Minimal JSON-RPC client for the wigolo MCP server.

    Communicates via stdin/stdout JSON-RPC 2.0 — no `mcp` SDK needed.
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._id = 0

    def _ensure_running(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        uvx = shutil.which("uvx")
        if uvx is None:
            raise FileNotFoundError("uvx not found — install with `pip install uv`")
        self._proc = subprocess.Popen(
            [uvx, "@KnockOutEZ/wigolo"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        time.sleep(1.0)  # Give server time to initialize

    def _call(self, method: str, params: dict | None = None) -> Any:
        if self._proc is None or self._proc.poll() is not None:
            raise ConnectionError("wigolo server not running")
        if self._proc.stdin is None or self._proc.stdout is None:
            raise ConnectionError("wigolo server pipes not initialized")
        self._id += 1
        msg = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        self._proc.stdin.write(msg + "\n")
        self._proc.stdin.flush()
        # Read one line of response
        line = self._proc.stdout.readline()
        if not line:
            raise ConnectionError("wigolo server returned empty response")
        resp = json.loads(line)
        return resp.get("result", {})

    def research(self, query: str, context: str = "") -> dict:
        self._ensure_running()
        return self._call("research", {"query": query, "context": context})

    def extract(self, url: str) -> str:
        self._ensure_running()
        result = self._call("extract", {"url": url})
        if isinstance(result, dict):
            return result.get("content", "")
        return str(result)

    def close(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            self._proc.wait(timeout=5)


class WigoloMCPToolkit:
    """Agno-compatible toolkit wrapping the wigolo MCP server.

    Exposes `research` and `extract` as callable tools.  If the wigolo
    server is not available, the methods gracefully degrade.
    """

    name = "wigolo"

    def __init__(self, client: Any = None) -> None:
        self._client = client if client is not None else _WigoloClient()
        # Fallback to stub if real client fails
        self._use_stub = False

    def research(self, query: str, context: str = "") -> dict:
        """Search wigolo for code examples, docs, or package info.

        Args:
            query: Search term (e.g. 'python-pptx usage examples')
            context: Additional context (optional)
        Returns:
            Dict with 'results' list, each containing 'title', 'url', 'content'.
        """
        try:
            return self._client.research(query=query, context=context)
        except Exception:
            logger.exception("wigolo research failed; falling back to stub")
            self._use_stub = True
            stub = getattr(self._client, "_stub", _StubClient())
            return stub.research(query, context)

    def extract(self, url: str) -> str:
        """Extract content from a URL using wigolo's extract tool.

        Args:
            url: URL to extract content from
        Returns:
            Extracted text content.
        """
        try:
            return self._client.extract(url=url)
        except Exception:
            logger.exception("wigolo extract failed; falling back to stub")
            self._use_stub = True
            stub = getattr(self._client, "_stub", _StubClient())
            return stub.extract(url)

    @property
    def tools(self) -> list[str]:
        """Return the names of tools this toolkit provides."""
        return ["wigolo_research", "wigolo_extract"]


def mcp_setup() -> tuple[WigoloMCPToolkit, list[str]]:
    """Initialize wigolo MCP toolkit and return (toolkit, tool_names).

    This is the entry point called by the Agno agent to register
    wigolo tools.  Returns a WigoloMCPToolkit instance and a list
    of Agno-tool names that map to the toolkit's methods.
    """
    wigolo_available = shutil.which("uvx") is not None
    client: Any
    if wigolo_available:
        client = _WigoloClient()
    else:
        client = None  # toolkit will use stub fallback
    toolkit = WigoloMCPToolkit(client=client)
    # The Agno tool names: the toolkit already prefixes with "wigolo"
    return toolkit, toolkit.tools
