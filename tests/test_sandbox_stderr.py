"""Tests that sandbox separates stdout and stderr (#17).

SPEC: docs/SPEC-25-improvements.md #17
Tier 2 — _exec_container must return stdout and stderr separately,
not merged into a single field.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from toolkinetik.sandbox import SandboxRunner


def _client_with_split_logs(stdout: bytes, stderr: bytes, exit_code: int = 0):
    """Mock client whose container.logs returns different values per stream."""
    container = MagicMock(name="container")
    container.wait.return_value = {"StatusCode": exit_code}

    def _logs(stdout=True, stderr=True, **_):
        if stdout and not stderr:
            return stdout_bytes
        if stderr and not stdout:
            return stderr_bytes
        return stdout_bytes + stderr_bytes

    stdout_bytes = stdout
    stderr_bytes = stderr
    container.logs.side_effect = _logs

    client = MagicMock(name="docker_client")
    client.containers.run.return_value = container
    return client, container


@pytest.fixture
def patched_split_client():
    with patch("toolkinetik.sandbox.docker") as mock_docker:
        client, _ = _client_with_split_logs(b"out-line\n", b"err-line\n")
        mock_docker.from_env.return_value = client
        yield client


class TestStdoutStderrSeparation:
    def test_stdout_and_stderr_separate(self, patched_split_client):
        runner = SandboxRunner()
        result = runner.run_code("print('out')")
        assert result["stdout"] == "out-line\n"
        assert result["stderr"] == "err-line\n"

    def test_empty_stderr_when_only_stdout(self, patched_split_client):
        with patch("toolkinetik.sandbox.docker") as mock_docker:
            client, _ = _client_with_split_logs(b"only-out\n", b"")
            mock_docker.from_env.return_value = client
            runner = SandboxRunner()
            result = runner.run_code("x")
        assert result["stdout"] == "only-out\n"
        assert result["stderr"] == ""

    def test_empty_stdout_when_only_stderr(self, patched_split_client):
        with patch("toolkinetik.sandbox.docker") as mock_docker:
            client, _ = _client_with_split_logs(b"", b"only-err\n")
            mock_docker.from_env.return_value = client
            runner = SandboxRunner()
            result = runner.run_code("x")
        assert result["stdout"] == ""
        assert result["stderr"] == "only-err\n"

    def test_run_tests_returns_separate_streams(self, patched_split_client):
        runner = SandboxRunner()
        runner._test_image_built = True
        result = runner.run_tests(test_code="def t(): pass", skill_code="def s(): pass")
        assert result["stdout"] == "out-line\n"
        assert result["stderr"] == "err-line\n"

    def test_result_keys_present(self, patched_split_client):
        runner = SandboxRunner()
        result = runner.run_code("x")
        assert "exit_code" in result
        assert "stdout" in result
        assert "stderr" in result