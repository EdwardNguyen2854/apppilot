"""
Process Manager for AppPilot.

Handles starting, stopping, and monitoring of external processes.
"""

import os
import sys
import subprocess
import signal
import psutil
import logging
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ProcessInfo:
    """Information about a managed process."""

    def __init__(self, app_id: str, process: subprocess.Popen, exe_path: str = None):
        self.app_id = app_id
        self.process = process
        self.pid = process.pid
        self.exe_path = exe_path
        self.started_at = datetime.now()
        self.psutil_process: Optional[psutil.Process] = None
        try:
            self.psutil_process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            pass

    def is_running(self) -> bool:
        """Check if the process is still running."""
        if self.process is None:
            return False
        return self.process.poll() is None

    def get_cpu_percent(self) -> float:
        """Get current CPU usage percentage."""
        if self.psutil_process and self.is_running():
            try:
                return self.psutil_process.cpu_percent(interval=0.1)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return 0.0
        return 0.0

    def get_memory_mb(self) -> float:
        """Get current memory usage in MB."""
        if self.psutil_process and self.is_running():
            try:
                return self.psutil_process.memory_info().rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return 0.0
        return 0.0

    def get_uptime(self) -> int:
        """Get process uptime in seconds."""
        if self.started_at:
            return int((datetime.now() - self.started_at).total_seconds())
        return 0


class ProcessManager:
    """Manages external processes for AppPilot."""

    def __init__(self):
        self._processes: Dict[str, ProcessInfo] = {}
        self._logs: Dict[str, List[str]] = {}
        self._log_files: Dict[str, Optional[str]] = {}
        logger.info("ProcessManager initialized")

    def start_process(self, app_id: str, exe_path: str, args: List[str] = None,
                      log_file: str = None, cwd: str = None) -> Tuple[bool, str]:
        """Start a new process."""
        if app_id in self._processes and self._processes[app_id].is_running():
            return False, f"Process {app_id} is already running with PID {self._processes[app_id].pid}"

        exe_path = self._resolve_exe_path(exe_path)
        if not Path(exe_path).exists():
            return False, f"Executable not found: {exe_path}"

        if log_file:
            log_dir = Path(log_file).parent
            log_dir.mkdir(parents=True, exist_ok=True)

        try:
            env = os.environ.copy()
            env['APPPILOT_APP_ID'] = app_id

            stdout_file = None
            stderr_file = None
            if log_file:
                stdout_file = open(log_file, 'a', encoding='utf-8')
                stderr_file = subprocess.STDOUT

            if cwd is None:
                cwd = str(Path(exe_path).parent)

            if args is None:
                args = []

            process = subprocess.Popen(
                [exe_path] + args,
                cwd=cwd,
                env=env,
                stdout=stdout_file if stdout_file else subprocess.DEVNULL,
                stderr=stderr_file if stderr_file else subprocess.DEVNULL,
                start_new_session=True
            )

            self._processes[app_id] = ProcessInfo(app_id, process, exe_path)
            self._log_files[app_id] = log_file
            self._logs[app_id] = []

            logger.info(f"Started {app_id} with PID {process.pid}")

            time.sleep(0.5)
            if process.poll() is not None:
                return False, f"Process started but immediately exited with code {process.returncode}"

            return True, f"Started {app_id} with PID {process.pid}"

        except Exception as e:
            logger.error(f"Failed to start {app_id}: {e}")
            return False, str(e)

    def _resolve_exe_path(self, exe_path: str) -> str:
        """Resolve executable path, handling relative paths."""
        if Path(exe_path).is_absolute():
            return exe_path

        if Path(exe_path).exists():
            return str(Path.cwd() / exe_path)

        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).parent.parent.parent

        resolved = base_dir / exe_path
        if resolved.exists():
            return str(resolved)

        return exe_path

    def stop_process(self, app_id: str, force: bool = False) -> Tuple[bool, str]:
        """Stop a running process."""
        if app_id not in self._processes:
            return False, f"No process found for {app_id}"

        proc_info = self._processes[app_id]

        if not proc_info.is_running():
            del self._processes[app_id]
            return False, f"Process {app_id} is not running"

        try:
            if force:
                os.kill(proc_info.pid, signal.SIGKILL)
                logger.info(f"Forcefully killed {app_id} (PID {proc_info.pid})")
            else:
                os.kill(proc_info.pid, signal.SIGTERM)
                logger.info(f"Sent SIGTERM to {app_id} (PID {proc_info.pid})")

            for _ in range(50):
                if proc_info.process.poll() is not None:
                    break
                time.sleep(0.1)

            if proc_info.process.poll() is None:
                os.kill(proc_info.pid, signal.SIGKILL)
                time.sleep(0.5)

            del self._processes[app_id]
            return True, f"Stopped {app_id}"

        except ProcessLookupError:
            del self._processes[app_id]
            return True, f"Process {app_id} already terminated"
        except Exception as e:
            logger.error(f"Failed to stop {app_id}: {e}")
            return False, str(e)

    def restart_process(self, app_id: str, exe_path: str, args: List[str] = None,
                        log_file: str = None) -> Tuple[bool, str]:
        """Restart a process."""
        if app_id in self._processes:
            self.stop_process(app_id, force=True)

        time.sleep(1)
        return self.start_process(app_id, exe_path, args, log_file)

    def get_process_status(self, app_id: str) -> Dict:
        """Get the current status of a process."""
        if app_id not in self._processes:
            return {
                'running': False,
                'app_id': app_id,
                'message': 'No process found'
            }

        proc_info = self._processes[app_id]

        if not proc_info.is_running():
            return {
                'running': False,
                'app_id': app_id,
                'pid': proc_info.pid,
                'exit_code': proc_info.process.returncode,
                'message': 'Process not running'
            }

        return {
            'running': True,
            'app_id': app_id,
            'pid': proc_info.pid,
            'cpu_percent': proc_info.get_cpu_percent(),
            'memory_mb': round(proc_info.get_memory_mb(), 2),
            'uptime_sec': proc_info.get_uptime(),
            'started_at': proc_info.started_at.isoformat()
        }

    def is_process_running(self, app_id: str) -> bool:
        """Check if a specific app's process is running."""
        if app_id not in self._processes:
            return False
        return self._processes[app_id].is_running()

    def get_all_processes(self) -> Dict[str, Dict]:
        """Get status of all managed processes."""
        result = {}
        for app_id in list(self._processes.keys()):
            result[app_id] = self.get_process_status(app_id)
        return result

    def get_process_pid(self, app_id: str) -> Optional[int]:
        """Get the PID of a process."""
        if app_id in self._processes:
            return self._processes[app_id].pid
        return None

    def read_logs(self, app_id: str, lines: int = 100) -> List[str]:
        """Read recent log lines for an app."""
        log_file = self._log_files.get(app_id)

        if not log_file:
            return ["No log file configured for this app"]

        try:
            if Path(log_file).exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                    return all_lines[-lines:]
            else:
                return [f"Log file not found: {log_file}"]
        except Exception as e:
            return [f"Error reading log file: {str(e)}"]

    def cleanup_dead_processes(self) -> List[str]:
        """Remove dead processes from tracking."""
        dead = []
        for app_id in list(self._processes.keys()):
            if not self._processes[app_id].is_running():
                del self._processes[app_id]
                dead.append(app_id)
        return dead

    def is_port_in_use(self, port: int) -> bool:
        """Check if a port is in use by any process."""
        for conn in psutil.net_connections():
            if conn.laddr.port == port:
                return True
        return False

    def get_system_stats(self) -> Dict:
        """Get overall system resource usage."""
        return {
            'cpu_percent': psutil.cpu_percent(interval=0.5),
            'memory_percent': psutil.virtual_memory().percent,
            'memory_available_mb': psutil.virtual_memory().available / (1024 * 1024),
            'disk_usage_percent': psutil.disk_usage('/').percent
        }