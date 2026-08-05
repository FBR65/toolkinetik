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
import re
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
    Supports both newline-delimited and Content-Length framing, skips
    server-initiated notifications (messages without `id`), and performs
    an `initialize` / `notifications/initialized` handshake on startup.
    """

    _INIT_TIMEOUT_S = 5.0  # max seconds to wait for initialize response
    _POLL_INTERVAL_S = 0.05  # sleep between readline attempts

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._id = 0
        self._initialized = False

    def _ensure_running(self) -> None:
        if self._proc is not None and self._proc.poll() is None and self._initialized:
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
        # Perform MCP handshake instead of a fixed time.sleep.
        self._handshake()

    def _handshake(self) -> None:
        """Send `initialize`, wait for the response, then send `notifications/initialized`."""
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise ConnectionError("wigolo server pipes not initialized")
        # Send initialize with a fresh id.
        self._id += 1
        init_id = self._id
        init_msg = json.dumps({
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "toolkinetik", "version": "0.1.0"}},
        })
        self._proc.stdin.write(init_msg + "\n")
        self._proc.stdin.flush()
        # Poll for the initialize response (skip notifications / blank lines).
        deadline = time.monotonic() + self._INIT_TIMEOUT_S
        while time.monotonic() < deadline:
            line = self._proc.stdout.readline()
            if not line:
                time.sleep(self._POLL_INTERVAL_S)
                continue
            msg = self._read_message(line)
            if msg is None:
                continue  # blank / unparseable — poll again
            if "id" not in msg:
                continue  # server notification, not our response
            if msg["id"] != init_id:
                continue  # response to a different request
            break
        else:
            raise ConnectionError("wigolo initialize handshake timed out")
        # Send initialized notification.
        notified = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._proc.stdin.write(notified + "\n")
        self._proc.stdin.flush()
        self._initialized = True

    def _read_message(self, line: str) -> dict | None:
        """Parse one JSON-RPC message from a stdout line.

        Supports Content-Length framing: a line starting with
        `Content-Length:` is the header of a framed message; the body
        follows on subsequent readline() calls.
        """
        if not line or not line.strip():
            return None
        # Content-Length framing: "Content-Length: N\r\n\r\n{body}".
        m = re.match(r"Content-Length:\s*(\d+)\s*\r?\n\r?\n(.*)", line, re.DOTALL)
        if m:
            declared = int(m.group(1))
            body_so_far = m.group(2)
            # If the body is shorter than declared, read more lines.
            while len(body_so_far) < declared and self._proc is not None and self._proc.stdout is not None:
                more = self._proc.stdout.readline()
                if not more:
                    break
                body_so_far += more
            try:
                return json.loads(body_so_far[:declared])
            except json.JSONDecodeError:
                return None
        # Newline-delimited JSON.
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def _call(self, method: str, params: dict | None = None) -> Any:
        if self._proc is None or self._proc.poll() is not None:
            raise ConnectionError("wigolo server not running")
        if self._proc.stdin is None or self._proc.stdout is None:
            raise ConnectionError("wigolo server pipes not initialized")
        self._id += 1
        call_id = self._id
        msg = json.dumps({"jsonrpc": "2.0", "id": call_id, "method": method, "params": params or {}})
        self._proc.stdin.write(msg + "\n")
        self._proc.stdin.flush()
        # Read lines until we get a response with our id (skip notifications,
        # blank lines, and unrelated responses).
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise ConnectionError("wigolo server returned empty response")
            parsed = self._read_message(line)
            if parsed is None:
                continue  # blank / unparseable
            if "id" not in parsed:
                continue  # server notification, not a response
            if parsed["id"] != call_id:
                continue  # response to a different request
            if "error" in parsed:
                raise ConnectionError(f"wigolo error: {parsed['error']}")
            return parsed.get("result", {})

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
        self._stub = _StubClient()
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
            return self._stub.research(query, context)

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
            return self._stub.extract(url)

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
