"""
CLI Runner for AppPilot.

Executes run-once CLI tool subprocesses with timeout, capturing
stdout, stderr, exit code, and duration. Used by the
``POST /api/apps/{id}/run`` endpoint.
"""

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT_SECONDS = 60.0


class CliRunner:
    """Spawn a CLI tool subprocess and capture its result."""

    def run(
        self,
        exe_path: str,
        args: Optional[List[str]] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Execute a CLI tool. Returns a dict of result fields.

        The runner never raises; every failure mode is captured into
        the returned dict so the caller can record it and respond
        uniformly.
        """
        resolved_exe = self._resolve_exe_path(exe_path)

        if not exe_path:
            return self._failure("Executable path is empty")

        effective_cwd = cwd or str(Path(resolved_exe).parent)
        command = [resolved_exe] + list(args or [])
        effective_env = env if env is not None else os.environ.copy()

        started = time.perf_counter()
        try:
            proc = subprocess.run(
                command,
                cwd=effective_cwd,
                env=effective_env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration_sec = round(time.perf_counter() - started, 3)
            logger.info(
                "CLI run finished: cmd=%s exit=%s duration=%.3fs",
                resolved_exe, proc.returncode, duration_sec,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout or "",
                "stderr": proc.stderr or "",
                "duration_sec": duration_sec,
                "success": proc.returncode == 0,
                "timed_out": False,
                "error_message": None,
            }
        except subprocess.TimeoutExpired as e:
            duration_sec = round(time.perf_counter() - started, 3)
            stdout = self._decode(e.stdout)
            stderr = self._decode(e.stderr)
            logger.warning(
                "CLI run timed out after %.1fs: cmd=%s", timeout, resolved_exe,
            )
            return {
                "exit_code": -1,
                "stdout": stdout,
                "stderr": stderr,
                "duration_sec": duration_sec,
                "success": False,
                "timed_out": True,
                "error_message": f"Process killed after {timeout}s timeout",
            }
        except FileNotFoundError as e:
            logger.warning("CLI run failed (executable missing): %s", e)
            return self._failure(str(e))
        except Exception as e:
            logger.error("CLI run failed: %s", e)
            return self._failure(str(e))

    def _failure(self, message: str) -> Dict[str, Any]:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "duration_sec": 0.0,
            "success": False,
            "timed_out": False,
            "error_message": message,
        }

    @staticmethod
    def _decode(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8", errors="replace")
            except Exception:
                return value.decode("latin-1", errors="replace")
        return str(value)

    @staticmethod
    def _resolve_exe_path(exe_path: str) -> str:
        """Resolve relative exe paths. Project-root first, then cwd."""
        if not exe_path:
            return exe_path
        if Path(exe_path).is_absolute():
            return exe_path
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).parent.parent.parent
        project_relative = base_dir / exe_path
        if project_relative.exists():
            return str(project_relative)
        cwd_relative = Path.cwd() / exe_path
        if cwd_relative.exists():
            return str(cwd_relative)
        return exe_path
