"""Tests for wigolo MCP integration (TDD: RED phase)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from toolkinetik.setup_mcp import WigoloMCPToolkit, mcp_setup


class TestWigoloMCPToolkit:
    """WigoloMCPToolkit: research and extract methods."""

    def test_toolkit_instance(self):
        """Toolkit can be instantiated with mocked client."""
        client = MagicMock()
        toolkit = WigoloMCPToolkit(client=client)
        assert toolkit is not None
        assert toolkit.name == "wigolo"

    def test_research_method_exists(self):
        """research method is callable."""
        toolkit = WigoloMCPToolkit(client=MagicMock())
        assert callable(getattr(toolkit, "research", None))

    def test_research_returns_dict(self):
        """research returns parsed JSON dict."""
        client = MagicMock()
        client.research.return_value = {"results": [{"title": "python-pptx"}]}
        toolkit = WigoloMCPToolkit(client=client)
        result = toolkit.research("python-pptx library")
        assert isinstance(result, dict)
        client.research.assert_called_once()

    def test_extract_method_exists(self):
        """extract method is callable."""
        toolkit = WigoloMCPToolkit(client=MagicMock())
        assert callable(getattr(toolkit, "extract", None))

    def test_extract_returns_str(self):
        """extract returns string content."""
        client = MagicMock()
        client.extract.return_value = "pptx.Presentation()"
        toolkit = WigoloMCPToolkit(client=client)
        result = toolkit.extract("https://pypi.org/project/python-pptx/")
        assert isinstance(result, str)


class TestMcpSetup:
    """mcp_setup: returns toolkit and tool list."""

    def test_mcp_setup_returns_toolkit_and_tools(self):
        """mcp_setup returns (WigoloMCPToolkit, list of tool names)."""
        toolkit, tools = mcp_setup()
        assert toolkit is not None
        assert isinstance(tools, list)
        assert "wigolo_research" in tools
        assert "wigolo_extract" in tools

    def test_mcp_setup_without_env(self):
        """Even without full MCP server, the setup returns a valid toolkit."""
        toolkit, tools = mcp_setup()
        assert toolkit.name == "wigolo"
        assert isinstance(tools, list)
        assert len(tools) >= 2
