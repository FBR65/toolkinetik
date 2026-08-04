"""Tests for Docker sandbox hardening (#3).

SPEC: docs/SPEC-25-improvements.md #3
Tier 3 — untrusted code must run with read_only, pids_limit, cap_drop=ALL,
no-new-privileges, and tmpfs noexec on /tmp.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from toolkinetik.sandbox import SandboxRunner


def _make_mock_client(exit_code: int = 0):
    container = MagicMock(name="container")
    container.wait.return_value = {"StatusCode": exit_code}
    container.logs.return_value = b"ok"
    client = MagicMock(name="docker_client")
    client.containers.run.return_value = container
    return client, container


@pytest.fixture
def patched_client():
    with patch("toolkinetik.sandbox.docker") as mock_docker:
        client, _ = _make_mock_client()
        mock_docker.from_env.return_value = client
        yield client


class TestSandboxHardening:
    def test_run_code_uses_read_only(self, patched_client):
        runner = SandboxRunner()
        runner.run_code("print('hi')")
        kwargs = patched_client.containers.run.call_args.kwargs
        assert kwargs.get("read_only") is True

    def test_run_code_uses_cap_drop_all(self, patched_client):
        runner = SandboxRunner()
        runner.run_code("x=1")
        kwargs = patched_client.containers.run.call_args.kwargs
        assert kwargs.get("cap_drop") == ["ALL"]

    def test_run_code_uses_no_new_privileges(self, patched_client):
        runner = SandboxRunner()
        runner.run_code("x=1")
        kwargs = patched_client.containers.run.call_args.kwargs
        assert "no-new-privileges" in kwargs.get("security_opt", [])

    def test_run_code_uses_pids_limit(self, patched_client):
        runner = SandboxRunner()
        runner.run_code("x=1")
        kwargs = patched_client.containers.run.call_args.kwargs
        assert kwargs.get("pids_limit") is not None
        assert kwargs.get("pids_limit") > 0

    def test_run_code_uses_tmpfs_noexec(self, patched_client):
        runner = SandboxRunner()
        runner.run_code("x=1")
        kwargs = patched_client.containers.run.call_args.kwargs
        tmpfs = kwargs.get("tmpfs", {})
        assert "/tmp" in tmpfs
        assert "noexec" in tmpfs["/tmp"]

    def test_run_tests_uses_hardening(self, patched_client):
        runner = SandboxRunner()
        runner._test_image_built = True  # skip build
        runner.run_tests(test_code="def t(): pass", skill_code="def s(): pass")
        kwargs = patched_client.containers.run.call_args.kwargs
        assert kwargs.get("read_only") is True
        assert kwargs.get("cap_drop") == ["ALL"]
        assert "no-new-privileges" in kwargs.get("security_opt", [])
        assert kwargs.get("pids_limit") > 0
        tmpfs = kwargs.get("tmpfs", {})
        assert "noexec" in tmpfs.get("/tmp", "")

    def test_network_mode_still_none(self, patched_client):
        runner = SandboxRunner()
        runner.run_code("x=1")
        kwargs = patched_client.containers.run.call_args.kwargs
        assert kwargs.get("network_mode") == "none"

    def test_mem_limit_still_256m(self, patched_client):
        runner = SandboxRunner()
        runner.run_code("x=1")
        kwargs = patched_client.containers.run.call_args.kwargs
        assert kwargs.get("mem_limit") == "256m"

    def test_existing_isolation_unaffected(self, patched_client):
        """Regression: existing isolation flags (network/mem/cpu) still present."""
        runner = SandboxRunner()
        runner.run_code("x=1")
        kwargs = patched_client.containers.run.call_args.kwargs
        assert kwargs.get("cpu_quota") == 50000