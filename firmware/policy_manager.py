import asyncio
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PolicyStatus:
    name: str
    pid: Optional[int]
    running: bool
    start_time: Optional[float]
    exit_code: Optional[int]
    last_error: Optional[str]


class SimplePolicyManager:
    """Manage a single policy subprocess with robust lifecycle handling."""

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._status: PolicyStatus = PolicyStatus(
            name="policy",
            pid=None,
            running=False,
            start_time=None,
            exit_code=None,
            last_error=None,
        )
        self._running = True

        # Default command mirrors existing usage: run firmware.main with websocket
        # Use kbot environment if available, fallback to system python
        kbot_python = Path.home() / "kbot" / "bin" / "python"
        python_cmd = str(kbot_python) if kbot_python.exists() else "python"
        
        # Default policy directory
        default_policy_dir = str(Path.home() / ".policies")
        
        # Run with sudo for IMU/CAN permissions and real-time priority
        self._default_cmd: List[str] = [
            "sudo",
            "-E",           # Preserve environment variables
            "chrt",         # Real-time scheduler
            "30",           # Priority level
            python_cmd,
            "-m",
            "firmware.main",
            "--websocket",
            default_policy_dir,
        ]

        # Run from the project directory that contains the `firmware` package
        # e.g., `<repo>/websocket-interface`
        self._default_cwd: str = str(Path(__file__).parent.parent.absolute())

    def start(self, cmd: Optional[List[str]] = None, cwd: Optional[str] = None) -> bool:
        """Start the policy subprocess if not already running.

        Args:
            cmd: Optional command list to execute. Defaults to a safe policy runner.
            cwd: Optional working directory. Defaults to the parent directory containing `firmware`.
        """
        try:
            if self._process is not None and self._process.poll() is None:
                # Already running
                return False

            command = cmd or list(self._default_cmd)
            workdir = cwd or self._default_cwd

            env = os.environ.copy()

            process = subprocess.Popen(
                command,
                cwd=workdir,
                env=env,
                preexec_fn=None,
            )

            self._process = process
            self._status = PolicyStatus(
                name="policy",
                pid=process.pid,
                running=True,
                start_time=time.time(),
                exit_code=None,
                last_error=None,
            )

            # Monitor in background
            asyncio.create_task(self._monitor(process))
            return True

        except Exception as exc:  # noqa: BLE001 - propagate as status for robustness
            self._status.last_error = str(exc)
            self._status.running = False
            self._status.pid = None
            return False

    def stop(self, timeout: int = 10) -> bool:
        """Stop the policy subprocess gracefully with a timeout."""
        process = self._process
        if process is None:
            return False

        try:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

            self._status.running = False
            self._status.exit_code = process.returncode
            self._process = None
            return True
        except Exception as exc:  # noqa: BLE001
            self._status.last_error = str(exc)
            return False

    def get_status(self) -> Dict[str, Any]:
        """Return a serializable snapshot of the policy status."""
        status = self._status
        return {
            "running": status.running,
            "pid": status.pid,
            "start_time": status.start_time,
            "exit_code": status.exit_code,
            "last_error": status.last_error,
            "uptime": (time.time() - status.start_time) if status.start_time else 0.0,
        }

    async def _monitor(self, process: subprocess.Popen) -> None:
        """Monitor lifecycle and update status when process exits."""
        try:
            while process.poll() is None and self._running:
                await asyncio.sleep(1.0)
            # Process ended
            self._status.running = False
            self._status.exit_code = process.returncode
            if self._process is process:
                self._process = None
        except Exception as exc:  # noqa: BLE001
            self._status.last_error = str(exc)


