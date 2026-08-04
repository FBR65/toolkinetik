"""Tests for the Docker sandbox runner — Docker SDK fully mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from toolkinetik.sandbox import SandboxRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(exit_code: int = 0, logs: str = "ok", wait_raises: Exception | None = None):
    """Return (mock_client, mock_container) simulating docker.from_env().

    The mock container's run()/wait()/logs()/remove() methods are configured
    so tests can inspect the calls. logs() returns the same bytes for both
    stdout and stderr streams (split via kwargs).
    """
    mock_container = MagicMock(name="container")

    # container.wait() returns {"StatusCode": exit_code, ...}
    if wait_raises is not None:
        mock_container.wait.side_effect = wait_raises
    else:
        mock_container.wait.return_value = {"StatusCode": exit_code}

    # container.logs() returns bytes split by stream kwarg.
    if isinstance(logs, str):
        logs_bytes = logs.encode()
    else:
        logs_bytes = logs

    def _logs(stdout=True, stderr=True, **_):
        # Default mock: both streams return the same payload so legacy
        # tests that check "X in stdout OR stderr" still work.
        return logs_bytes

    mock_container.logs.side_effect = _logs

    mock_client = MagicMock(name="docker_client")
    mock_client.containers.run.return_value = mock_container
    return mock_client, mock_container


def _decode_logs(raw) -> str:
    """Decode docker logs (bytes or list of bytes) to a string."""
    if isinstance(raw, bytes):
        return raw.decode(errors="replace")
    if isinstance(raw, (list, tuple)):
        return b"".join(raw).decode(errors="replace")
    return str(raw)


# ---------------------------------------------------------------------------
# Task 3.1 — SandboxRunner tests
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_client():
    """Patch docker.from_env so SandboxRunner can be instantiated without Docker."""
    with patch("toolkinetik.sandbox.docker") as mock_docker:
        client, container = _make_mock_client()
        mock_docker.from_env.return_value = client
        yield client, container, mock_docker


class TestRunCode:
    def test_run_code_success(self, patched_client):
        _client, container, _ = patched_client
        container.wait.return_value = {"StatusCode": 0}
        container.logs.side_effect = lambda stdout=True, stderr=True, **_: b"hello"

        sandbox = SandboxRunner()
        result = sandbox.run_code("print('hello')")

        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]
        assert result["exit_code"] == 0

    def test_run_code_failure(self, patched_client):
        _client, container, _ = patched_client
        container.wait.return_value = {"StatusCode": 1}
        container.logs.side_effect = lambda stdout=True, stderr=True, **_: b"error message"

        sandbox = SandboxRunner()
        result = sandbox.run_code("raise ValueError('boom')")

        assert result["exit_code"] == 1
        assert "error" in result["stdout"].lower() or "error" in result["stderr"].lower() or result["exit_code"] == 1

    def test_run_code_timeout(self, patched_client):
        """When container.wait raises, cleanup still runs."""
        _client, container, _ = patched_client
        container.wait.side_effect = Exception("timeout reached")

        sandbox = SandboxRunner()
        result = sandbox.run_code("while True: pass", timeout=1)

        # Container should be removed (cleanup) even on failure.
        assert container.remove.called
        # Should report a timeout error.
        assert result["exit_code"] != 0
        assert "timeout" in result["stderr"].lower() or "timeout" in result["stdout"].lower() or "exception" in result["stderr"].lower()


class TestRunTests:
    def test_run_tests_success(self, patched_client):
        _client, container, _ = patched_client
        container.wait.return_value = {"StatusCode": 0}
        container.logs.side_effect = lambda stdout=True, stderr=True, **_: b"1 passed"

        sandbox = SandboxRunner()
        result = sandbox.run_tests(
            test_code="def test_x(): assert True",
            skill_code="def x(): return 1",
        )

        assert result["exit_code"] == 0
        assert "1 passed" in result["stdout"]

    def test_run_tests_failure(self, patched_client):
        _client, container, _ = patched_client
        container.wait.return_value = {"StatusCode": 1}
        container.logs.side_effect = lambda stdout=True, stderr=True, **_: b"AssertionError: boom"

        sandbox = SandboxRunner()
        result = sandbox.run_tests(
            test_code="def test_x(): assert False",
            skill_code="def x(): return 1",
        )

        assert result["exit_code"] == 1
        assert "AssertionError" in result["stdout"] or "AssertionError" in result["stderr"]


class TestSandboxConfig:
    def test_sandbox_uses_correct_image(self, patched_client):
        client, _container, _ = patched_client

        sandbox = SandboxRunner()
        sandbox.run_code("print(1)")

        _args, kwargs = client.containers.run.call_args
        assert kwargs.get("image") == "python:3.12-slim"

    def test_sandbox_network_isolated(self, patched_client):
        client, _container, _ = patched_client

        sandbox = SandboxRunner()
        sandbox.run_code("print(1)")

        _args, kwargs = client.containers.run.call_args
        assert kwargs.get("network_mode") == "none"

    def test_sandbox_memory_limited(self, patched_client):
        client, _container, _ = patched_client

        sandbox = SandboxRunner()
        sandbox.run_code("print(1)")

        _args, kwargs = client.containers.run.call_args
        assert kwargs.get("mem_limit") == "256m"
        assert kwargs.get("cpu_quota") == 50000