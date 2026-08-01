"""Tests for the NiceGUI dashboard (ui.py).

NiceGUI is hard to test directly (starts a server on import), so we
only verify that the module is importable and exposes the expected
constants and page function.
"""

from __future__ import annotations

import importlib


def test_ui_module_imports() -> None:
    """The ui module imports without errors and without starting a server."""
    mod = importlib.import_module("toolkinetik.ui")
    assert mod is not None


def test_ui_has_page_decorator() -> None:
    """The module defines a main_page function."""
    mod = importlib.import_module("toolkinetik.ui")
    assert hasattr(mod, "main_page")
    assert callable(mod.main_page)


def test_ui_api_base_constant() -> None:
    """API_BASE is defined as a string."""
    mod = importlib.import_module("toolkinetik.ui")
    assert hasattr(mod, "API_BASE")
    assert isinstance(mod.API_BASE, str)


def test_ui_headers_constant() -> None:
    """HEADERS dict contains an X-API-Key entry."""
    mod = importlib.import_module("toolkinetik.ui")
    assert hasattr(mod, "HEADERS")
    assert isinstance(mod.HEADERS, dict)
    assert "X-API-Key" in mod.HEADERS