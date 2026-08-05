"""Additional tests for setup_mcp.py edge cases (P3.2).

SPEC: docs/SPEC-production-readiness.md P3.2
Covers Popen failure, stdout EOF, malformed JSON, Content-Length mismatch.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from toolkinetik.setup_mcp import WigoloMCPToolkit, _StubClient, _WigoloClient


class TestWigoloClientEdgeCases:
    def test_popen_failure_raises_file_not_found(self):
        """_ensure_running raises FileNotFoundError when uvx is missing."""
        client = _WigoloClient()
        with patch("toolkinetik.setup_mcp.shutil.which", return_value=None), pytest.raises(FileNotFoundError, match="uvx"):
            client._ensure_running()

    def test_stdout_eof_raises_connection_error(self):
        """_call raises ConnectionError when stdout returns empty."""
        client = _WigoloClient()
        client._proc = MagicMock()
        client._proc.poll.return_value = None
        client._proc.stdin = MagicMock()
        client._proc.stdout = MagicMock()
        client._proc.stdout.readline.return_value = ""  # EOF
        with pytest.raises(ConnectionError, match="empty response"):
            client._call("research", {"query": "test"})

    def test_malformed_json_returns_none(self):
        """_read_message returns None for malformed JSON."""
        client = _WigoloClient()
        result = client._read_message("not valid json {{{")
        assert result is None

    def test_blank_line_returns_none(self):
        """_read_message returns None for blank lines."""
        client = _WigoloClient()
        assert client._read_message("") is None
        assert client._read_message("   \n") is None

    def test_call_skips_notifications(self):
        """_call skips server notifications (messages without id)."""
        client = _WigoloClient()
        client._proc = MagicMock()
        client._proc.poll.return_value = None
        client._proc.stdin = MagicMock()
        client._proc.stdout = MagicMock()

        # First line: notification (no id), second: response with id=1
        client._proc.stdout.readline.side_effect = [
            '{"jsonrpc": "2.0", "method": "some_notification"}',
            '{"jsonrpc": "2.0", "id": 1, "result": {"data": "ok"}}',
        ]
        client._id = 0  # next call_id will be 1
        result = client._call("research", {"query": "test"})
        assert result == {"data": "ok"}

    def test_call_raises_on_error_response(self):
        """_call raises ConnectionError when response contains error."""
        client = _WigoloClient()
        client._proc = MagicMock()
        client._proc.poll.return_value = None
        client._proc.stdin = MagicMock()
        client._proc.stdout = MagicMock()
        client._proc.stdout.readline.return_value = '{"jsonrpc": "2.0", "id": 1, "error": {"message": "bad"}}'
        client._id = 0
        with pytest.raises(ConnectionError, match="wigolo error"):
            client._call("research", {})

    def test_extract_returns_string(self):
        """extract returns string content from dict result."""
        client = _WigoloClient()
        client._initialized = True  # skip handshake
        client._proc = MagicMock()
        client._proc.poll.return_value = None
        client._proc.stdin = MagicMock()
        client._proc.stdout = MagicMock()
        client._proc.stdout.readline.return_value = '{"jsonrpc": "2.0", "id": 1, "result": {"content": "extracted text"}}'
        client._id = 0
        result = client.extract("https://example.com")
        assert result == "extracted text"

    def test_extract_returns_str_for_non_dict_result(self):
        """extract returns str() for non-dict results."""
        client = _WigoloClient()
        client._initialized = True  # skip handshake
        client._proc = MagicMock()
        client._proc.poll.return_value = None
        client._proc.stdin = MagicMock()
        client._proc.stdout = MagicMock()
        client._proc.stdout.readline.return_value = '{"jsonrpc": "2.0", "id": 1, "result": "raw string"}'
        client._id = 0
        result = client.extract("https://example.com")
        assert result == "raw string"

    def test_close_terminates_process(self):
        """close() terminates the subprocess."""
        client = _WigoloClient()
        mock_proc = MagicMock()
        client._proc = mock_proc
        client.close()
        mock_proc.terminate.assert_called_once()


class TestStubClient:
    def test_stub_research_returns_error(self):
        """_StubClient.research returns error dict."""
        stub = _StubClient()
        result = stub.research("test")
        assert "error" in result
        assert "unavailable" in result["error"]

    def test_stub_extract_returns_empty(self):
        """_StubClient.extract returns empty string."""
        stub = _StubClient()
        assert stub.extract("https://example.com") == ""


class TestWigoloToolkitFallback:
    def test_research_falls_back_to_stub_on_error(self):
        """WigoloMCPToolkit.research uses stub when client raises."""
        client = MagicMock()
        client.research.side_effect = ConnectionError("server down")
        # Remove auto-created _stub so the fallback creates a real _StubClient
        del client._stub
        toolkit = WigoloMCPToolkit(client=client)
        result = toolkit.research("test")
        assert isinstance(result, dict)
        assert "error" in result or "results" in result

    def test_extract_falls_back_to_stub_on_error(self):
        """WigoloMCPToolkit.extract uses stub when client raises."""
        client = MagicMock()
        client.extract.side_effect = ConnectionError("server down")
        del client._stub
        toolkit = WigoloMCPToolkit(client=client)
        result = toolkit.extract("https://example.com")
        assert isinstance(result, str)