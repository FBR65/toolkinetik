"""Tests that sandbox reports build failures instead of silent fallback (#6)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from toolkinetik.sandbox import SandboxRunner


def _client_build_fails():
    client = MagicMock(name="docker_client")
    client.images.get.side_effect = Exception("not found")
    client.images.build.side_effect = RuntimeError("network unavailable")
    container = MagicMock(name="container")
    container.wait.return_value = {"StatusCode": 0}
    container.logs.side_effect = lambda stdout=True, stderr=True, **_: b""
    client.containers.run.return_value = container
    return client


class TestSandboxBuildFailure:
    def test_ensure_test_image_raises_on_build_failure(self):
        with patch("toolkinetik.sandbox.docker") as mock_docker:
            client = _client_build_fails()
            mock_docker.from_env.return_value = client
            runner = SandboxRunner()
            with pytest.raises(RuntimeError, match="image build failed"):
                runner._ensure_test_image()

    def test_run_tests_propagates_build_failure(self):
        with patch("toolkinetik.sandbox.docker") as mock_docker:
            client = _client_build_fails()
            mock_docker.from_env.return_value = client
            runner = SandboxRunner()
            result = runner.run_tests(
                test_code="def t(): pass",
                skill_code="def s(): pass",
            )
            assert result["exit_code"] != 0
            assert "image build failed" in result["stderr"].lower() or "build" in result["stderr"].lower()

    def test_existing_image_no_build_no_error(self):
        with patch("toolkinetik.sandbox.docker") as mock_docker:
            client = MagicMock()
            client.images.get.return_value = MagicMock()  # image exists
            container = MagicMock()
            container.wait.return_value = {"StatusCode": 0}
            container.logs.side_effect = lambda stdout=True, stderr=True, **_: b"ok"
            client.containers.run.return_value = container
            mock_docker.from_env.return_value = client
            runner = SandboxRunner()
            tag = runner._ensure_test_image()
            assert tag == "toolkinetik-sandbox:latest"
            client.images.build.assert_not_called()