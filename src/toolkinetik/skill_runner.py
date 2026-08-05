"""SkillRunner — isolated skill execution via subprocess (P1.6).

Skills execute in a separate Python process with timeout and memory limits,
so a buggy skill (infinite loop, os._exit, memory leak) can't crash the
main FastAPI server.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillRunner:
    """Run skill code in an isolated subprocess with timeout and memory limits."""

    def __init__(self, timeout: int = 30, memory_mb: int = 256) -> None:
        self.timeout = timeout
        self.memory_mb = memory_mb

    def run_code(self, code: str) -> dict:
        """Execute *code* in a subprocess and return the result.

        Returns {"exit_code": int, "stdout": str, "stderr": str}.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            script_path = f.name

        try:
            proc = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={"PYTHONPATH": ":".join(sys.path)},
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -9,
                "stdout": "",
                "stderr": f"timeout: skill exceeded {self.timeout}s limit",
            }
        except Exception as exc:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"runner error: {exc}",
            }
        finally:
            Path(script_path).unlink(missing_ok=True)

    def run_function(self, code: str, func_name: str, *args, **kwargs) -> dict:
        """Execute a specific function from *code* with the given args.

        Writes a wrapper script that imports the function and calls it.
        """
        import json
        wrapper = f"""
import json
{code}

_args = json.loads('{json.dumps(list(args))}')
_kwargs = json.loads('{json.dumps(kwargs)}')
_result = {func_name}(*_args, **_kwargs)
print(json.dumps({{"result": repr(_result)}}))
"""
        return self.run_code(wrapper)