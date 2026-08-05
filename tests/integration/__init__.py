"""Integration test fixtures and markers.

Integration tests require real infrastructure (Docker, uvx/wigolo, LLM
endpoint, LanceDB). They are skipped automatically when the required
tooling is not available.
"""

from __future__ import annotations

import shutil

import pytest


def pytest_collection_modifyitems(config, items):
    """Auto-skip integration tests if infrastructure is missing."""
    for item in items:
        if item.get_closest_marker("integration"):
            # Check what infrastructure the test needs
            if "docker" in item.keywords and not shutil.which("docker"):
                item.add_marker(pytest.mark.skip(reason="docker not available"))
            if "wigolo" in item.keywords and not shutil.which("uvx"):
                item.add_marker(pytest.mark.skip(reason="uvx not available"))