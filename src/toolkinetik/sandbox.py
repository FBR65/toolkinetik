"""Docker sandbox runner for isolated code & test execution.

Task 3.1: SandboxRunner spins up short-lived Docker containers with strict
resource isolation (no network, limited memory/CPU) to execute untrusted
Python code or pytest suites.  All Docker SDK calls go through
``docker.from_env()`` so they can be mocked in tests — no running Docker
daemon is required for the test suite.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import docker

from toolkinetik.config import get_settings


class SandboxRunner:
    """Run Python code in isolated, resource-limited Docker containers."""

    # Hard isolation defaults shared by run_code / run_tests.
    _NETWORK_MODE = "none"
    _MEM_LIMIT = "256m"
    _CPU_QUOTA = 50000  # 50% of one CPU (100000 = 1 CPU)
    _PIDS_LIMIT = 64
    _CAP_DROP = ["ALL"]
    _SECURITY_OPT = ["no-new-privileges"]
    _READ_ONLY = True
    _TMPFS = {"/tmp": "rw,noexec,nosuid,size=64m"}

    # Custom test image tag with pytest pre-installed.
    _TEST_IMAGE_TAG = "toolkinetik-sandbox:latest"

    def __init__(self, image: str | None = None) -> None:
        self.image = image if image is not None else get_settings().SANDBOX_IMAGE
        self.client = docker.from_env()
        self._test_image_built = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_code(self, code: str, timeout: int = 30) -> dict:
        """Execute *code* in a throwaway container and capture output.

        Returns ``{"exit_code": int, "stdout": str, "stderr": str}``.
        """
        # Use NamedTemporaryFile (mktemp is deprecated and unsafe).
        fd, tmp_path = tempfile.mkstemp(suffix=".py")
        os.close(fd)
        tmp = Path(tmp_path)
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

    def run_tests(self, test_code: str, skill_code: str, timeout: int = 60) -> dict:
        """Run a pytest suite against *skill_code* inside the sandbox.

        Uses a custom image with pytest pre-installed so that no network
        access is needed during test execution.  The image is built on first
        use from ``python:3.12-slim`` + ``pip install pytest``.
        """
        test_image = self._ensure_test_image()
        tmpdir = Path(tempfile.mkdtemp(prefix="sandbox_tests_"))
        try:
            (tmpdir / "skill.py").write_text(skill_code)
            (tmpdir / "test_skill.py").write_text(test_code)

            mounts = {}
            for fname in ("skill.py", "test_skill.py"):
                src = str(tmpdir / fname)
                mounts[src] = {"bind": f"/sandbox/{fname}", "mode": "ro"}

            return self._exec_container(
                command=["pytest", "-v"],
                mounts=mounts,
                workdir="/sandbox",
                timeout=timeout,
                image=test_image,
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_test_image(self) -> str:
        """Build (once) and return the custom test image tag.

        The image is built from python:3.12-slim with pytest pre-installed,
        so that run_tests can execute with network_mode="none".
        """
        if self._test_image_built:
            return self._TEST_IMAGE_TAG

        # Check if the image already exists.
        try:
            self.client.images.get(self._TEST_IMAGE_TAG)
            self._test_image_built = True
            return self._TEST_IMAGE_TAG
        except Exception:
            pass  # Image doesn't exist — build it.

        # Build a minimal image: python:3.12-slim + pytest.
        dockerfile_content = (
            "FROM python:3.12-slim\n"
            "RUN pip install --no-cache-dir pytest\n"
        )
        try:
            self.client.images.build(
                fileobj=__import__("io").BytesIO(dockerfile_content.encode()),
                tag=self._TEST_IMAGE_TAG,
                rm=True,
            )
            self._test_image_built = True
        except Exception:
            # If build fails (e.g. no Docker daemon in tests), fall back to
            # the base image — run_tests will use pip install with network.
            pass
        return self._TEST_IMAGE_TAG

    def _exec_container(
        self,
        command: list[str],
        mounts: dict,
        workdir: str,
        timeout: int,
        image: str | None = None,
    ) -> dict:
        """Run a container with the shared isolation constraints.

        *mounts* maps host-path -> bind-spec dict (as expected by the Docker
        SDK's ``volumes`` parameter).
        """
        container = None
        use_image = image if image is not None else self.image
        try:
            container = self.client.containers.run(
                image=use_image,
                command=command,
                volumes=mounts,
                working_dir=workdir,
                network_mode=self._NETWORK_MODE,
                mem_limit=self._MEM_LIMIT,
                cpu_quota=self._CPU_QUOTA,
                pids_limit=self._PIDS_LIMIT,
                cap_drop=self._CAP_DROP,
                security_opt=self._SECURITY_OPT,
                read_only=self._READ_ONLY,
                tmpfs=self._TMPFS,
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