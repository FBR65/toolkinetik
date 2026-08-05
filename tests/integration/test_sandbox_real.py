"""Integration tests for the Docker sandbox against a real Docker daemon.

SPEC: docs/SPEC-production-readiness.md P0.1
Tier 3 — the sandbox hardening flags (read_only, cap_drop, tmpfs noexec,
network_mode=none, pids_limit) must actually work with a real Docker daemon.

These tests are skipped if Docker is not available or the Docker SDK
cannot connect to the daemon.
"""

from __future__ import annotations

import shutil

import pytest


def _docker_reachable() -> bool:
    """Check that docker CLI exists AND the Python SDK can connect."""
    if not shutil.which("docker"):
        return False
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


docker_available = _docker_reachable()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not docker_available, reason="docker daemon not reachable"),
]


@pytest.mark.docker
class TestRealSandboxHardening:
    def test_pytest_runs_in_sandbox(self):
        """A real pytest run inside the sandbox completes with exit 0."""
        from toolkinetik.sandbox import SandboxRunner

        runner = SandboxRunner()
        result = runner.run_tests(
            test_code="def test_pass(): assert True\n",
            skill_code="def add(a, b): return a + b\n",
            timeout=120,
        )
        assert result["exit_code"] == 0, f"stderr: {result['stderr']}"

    def test_network_isolation_blocks_dns(self):
        """network_mode='none' blocks outbound DNS resolution."""
        from toolkinetik.sandbox import SandboxRunner

        runner = SandboxRunner()
        result = runner.run_code(
            "import socket\nsocket.gethostbyname('example.com')\n",
            timeout=30,
        )
        assert result["exit_code"] != 0
        assert "gaierror" in result["stderr"] or "socket" in result["stderr"].lower()

    def test_read_only_blocks_write_to_etc(self):
        """read_only=True blocks writes to /etc/passwd."""
        from toolkinetik.sandbox import SandboxRunner

        runner = SandboxRunner()
        result = runner.run_code(
            "open('/etc/passwd', 'a').write('test')\n",
            timeout=30,
        )
        assert result["exit_code"] != 0

    def test_cap_drop_blocks_setuid(self):
        """cap_drop=['ALL'] blocks os.setuid."""
        from toolkinetik.sandbox import SandboxRunner

        runner = SandboxRunner()
        result = runner.run_code(
            "import os\nos.setuid(0)\n",
            timeout=30,
        )
        assert result["exit_code"] != 0