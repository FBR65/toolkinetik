"""Tests for _WigoloClient JSON-RPC framing, handshake, and poll-start (#16).

SPEC: docs/SPEC-25-improvements.md #16
Tier 2 — _WigoloClient must do initialize/initialized handshake, skip
notifications, support Content-Length framing, and poll for readiness
instead of time.sleep(1.0).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from toolkinetik.setup_mcp import _WigoloClient

SRC = Path(__file__).resolve().parent.parent / "src" / "toolkinetik" / "setup_mcp.py"


def _pipepair(lines_out):
    """Return (stdin_mock, stdout_mock) where stdout yields the given lines."""
    stdin = MagicMock()
    stdin.write = MagicMock()
    stdin.flush = MagicMock()
    stdout = MagicMock()
    iterator = iter(lines_out + [""])
    stdout.readline.side_effect = lambda: next(iterator)
    return stdin, stdout


def _client_with_pipes(lines_out):
    client = _WigoloClient()
    stdin, stdout = _pipepair(lines_out)
    client._proc = MagicMock()
    client._proc.poll.return_value = None  # still running
    client._proc.stdin = stdin
    client._proc.stdout = stdout
    return client, stdin


class TestCallSkipNotifications:
    def test_call_skips_notification_lines(self):
        notification = json.dumps({"jsonrpc": "2.0", "method": "progress", "params": {}})
        response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        client, _ = _client_with_pipes([notification, response])
        result = client._call("research", {"query": "x"})
        assert result == {"ok": True}

    def test_call_raises_on_empty_response(self):
        client, _ = _client_with_pipes([])
        with pytest.raises(ConnectionError, match="empty"):
            client._call("research", {"query": "x"})

    def test_call_sends_jsonrpc_with_id(self):
        response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})
        client, stdin = _client_with_pipes([response])
        client._call("research", {"query": "x"})
        sent = stdin.write.call_args[0][0]
        assert "jsonrpc" in sent
        assert '"id": 1' in sent
        assert "research" in sent


class TestContentLengthFraming:
    def test_call_handles_content_length_framing(self):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"data": 42}})
        framed = f"Content-Length: {len(body)}\r\n\r\n{body}"
        client, _ = _client_with_pipes([framed])
        result = client._call("research", {"query": "x"})
        assert result == {"data": 42}

    def test_content_length_multiline_body(self):
        # _call increments _id from 0 to 1 on first call, so the response id must be 1.
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"nested": {"x": 1}}})
        framed = f"Content-Length: {len(body)}\r\n\r\n{body}"
        client, _ = _client_with_pipes([framed])
        result = client._call("extract", {"url": "http://x"})
        assert result == {"nested": {"x": 1}}


class TestHandshake:
    def test_ensure_running_sends_initialize(self):
        """_ensure_running must send an initialize JSON-RPC request on startup."""
        client = _WigoloClient()
        proc = MagicMock()
        proc.poll.return_value = None
        stdin, _ = _pipepair([])
        proc.stdin = stdin
        stdout = MagicMock()
        init_resp = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "wigolo"}}
        })
        notified = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        stdout.readline.side_effect = [init_resp, notified, ""]
        proc.stdout = stdout

        with patch("toolkinetik.setup_mcp.subprocess.Popen", return_value=proc), \
             patch("toolkinetik.setup_mcp.shutil.which", return_value="/fake/uvx"):
            client._ensure_running()

        sent_msgs = [c[0][0] for c in stdin.write.call_args_list]
        assert any('"method": "initialize"' in s or '"method":"initialize"' in s.replace(" ", "")
                   for s in sent_msgs), f"must send initialize; got: {sent_msgs}"

    def test_ensure_running_sends_initialized_notification(self):
        client = _WigoloClient()
        proc = MagicMock()
        proc.poll.return_value = None
        stdin, _ = _pipepair([])
        proc.stdin = stdin
        stdout = MagicMock()
        init_resp = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "wigolo"}}
        })
        notified = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        stdout.readline.side_effect = [init_resp, notified, ""]
        proc.stdout = stdout

        with patch("toolkinetik.setup_mcp.subprocess.Popen", return_value=proc), \
             patch("toolkinetik.setup_mcp.shutil.which", return_value="/fake/uvx"):
            client._ensure_running()

        sent_msgs = [c[0][0] for c in stdin.write.call_args_list]
        assert any("notifications/initialized" in s for s in sent_msgs), \
            f"must send initialized notification; got: {sent_msgs}"


class TestPollInsteadOfSleep:
    def test_no_fixed_sleep_in_ensure_running(self):
        src = SRC.read_text()
        m = re.search(r"def _ensure_running\(self\).*?(?=\n    def |\nclass )", src, re.DOTALL)
        assert m, "_ensure_running method not found"
        body = m.group(0)
        # No bare 1-second sleep; short poll-interval sleeps are fine.
        assert "sleep(1.0)" not in body, \
            "_ensure_running must not use the fixed time.sleep(1.0) start delay"

    def test_ensure_running_polls_until_ready_or_timeout(self):
        client = _WigoloClient()
        proc = MagicMock()
        proc.poll.return_value = None
        stdin, _ = _pipepair([])
        proc.stdin = stdin
        stdout = MagicMock()
        init_resp = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "wigolo"}}
        })
        notified = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        stdout.readline.side_effect = ["", init_resp, notified, ""]
        proc.stdout = stdout

        with patch("toolkinetik.setup_mcp.subprocess.Popen", return_value=proc), \
             patch("toolkinetik.setup_mcp.shutil.which", return_value="/fake/uvx"):
            client._ensure_running()
        sent_msgs = [c[0][0] for c in stdin.write.call_args_list]
        assert any("initialize" in s for s in sent_msgs)


class TestStubFallbackRegression:
    def test_stub_still_works_when_uvx_missing(self):
        from toolkinetik.setup_mcp import WigoloMCPToolkit
        with patch("toolkinetik.setup_mcp.shutil.which", return_value=None):
            toolkit = WigoloMCPToolkit()
            result = toolkit.research("anything")
        assert "error" in result or "unavailable" in str(result)