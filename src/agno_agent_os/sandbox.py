"""Docker sandbox runner for isolated code & test execution.

Task 3.1: SandboxRunner spins up short-lived Docker containers with strict
resource isolation (no network, limited memory/CPU) to execute untrusted
Python code or pytest suites.  All Docker SDK calls go through
``docker.from_env()`` so they can be mocked in tests — no running Docker
daemon is required for the test suite.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict

import docker

from agno_agent_os.config import get_settings


class SandboxRunner:
    """Run Python code in isolated, resource-limited Docker containers."""

    # Hard isolation defaults shared by run_code / run_tests.
    _NETWORK_MODE = "none"
    _MEM_LIMIT = "256m"
    _CPU_QUOTA = 50000  # 50% of one CPU (100000 = 1 CPU)

    def __init__(self, image: str | None = None) -> None:
        self.image = image if image is not None else get_settings().SANDBOX_IMAGE
        self.client = docker.from_env()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_code(self, code: str, timeout: int = 30) -> Dict:
        """Execute *code* in a throwaway container and capture output.

        Returns ``{"exit_code": int, "stdout": str, "stderr": str}``.
        """
        tmp = Path(tempfile.mktemp(suffix=".py"))
        try:
            tmp.write_text(code)
            return self._exec_container(
                command=["python", tmp.name],
                mounts={str(tmp): {"bind": f"/sandbox/{tmp.name}", "mode": "ro"}},
                workdir="/sandbox",
                timeout=timeout,
            )
        finally:
            if tmp.exists():
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def run_tests(self, test_code: str, skill_code: str, timeout: int = 60) -> Dict:
        """Run a pytest suite against *skill_code* inside the sandbox.

        Creates a temp directory with ``skill.py``, ``test_skill.py`` and a
        ``requirements.txt`` containing ``pytest``, then executes
        ``bash -c 'pip install -q pytest && pytest -v'``.
        """
        tmpdir = Path(tempfile.mkdtemp(prefix="sandbox_tests_"))
        try:
            (tmpdir / "skill.py").write_text(skill_code)
            (tmpdir / "test_skill.py").write_text(test_code)
            (tmpdir / "requirements.txt").write_text("pytest\n")

            mounts = {}
            for fname in ("skill.py", "test_skill.py", "requirements.txt"):
                src = str(tmpdir / fname)
                mounts[src] = {"bind": f"/sandbox/{fname}", "mode": "ro"}

            return self._exec_container(
                command=["bash", "-c", "pip install -q pytest && pytest -v"],
                mounts=mounts,
                workdir="/sandbox",
                timeout=timeout,
            )
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _exec_container(
        self,
        command: list,
        mounts: dict,
        workdir: str,
        timeout: int,
    ) -> Dict:
        """Run a container with the shared isolation constraints.

        *mounts* maps host-path -> bind-spec dict (as expected by the Docker
        SDK's ``volumes`` parameter).
        """
        container = None
        try:
            container = self.client.containers.run(
                image=self.image,
                command=command,
                volumes=mounts,
                working_dir=workdir,
                network_mode=self._NETWORK_MODE,
                mem_limit=self._MEM_LIMIT,
                cpu_quota=self._CPU_QUOTA,
                detach=True,
                tty=False,
            )
            # Wait for completion.  docker SDK wait() returns {"StatusCode": N}.
            result = container.wait(timeout=timeout)
            exit_code = int(result.get("StatusCode", -1))
            logs_raw = container.logs(stdout=True, stderr=True)
            stdout = self._decode_logs(logs_raw)
            return {"exit_code": exit_code, "stdout": stdout, "stderr": ""}
        except Exception as exc:
            # Timeout or docker error — return a structured failure.
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"timeout/exception: {exc}",
            }
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    @staticmethod
    def _decode_logs(raw) -> str:
        """Decode docker logs (bytes or iterable of bytes) to a string."""
        if isinstance(raw, bytes):
            return raw.decode(errors="replace")
        if isinstance(raw, (list, tuple)):
            return b"".join(raw).decode(errors="replace")
        return str(raw)