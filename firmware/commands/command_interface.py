"""Abstract interface for command input sources (keyboard, UDP, etc.)."""

import threading
from abc import ABC, abstractmethod
from typing import Optional

from firmware.actuators import RobotConfig

# Example policy command names:
#     "xvel",
#     "yvel",
#     "yawrate",
#     "baseheight",
#     "baseroll",
#     "basepitch",
#     "rshoulderpitch",  # 21
#     "rshoulderroll",  # 22
#     "rshoulderyaw",  # 23
#     "relbowpitch",  # 24
#     "rwristroll",  # 25
#     "lshoulderpitch",  # 11
#     "lshoulderroll",  # 12
#     "lshoulderyaw",  # 13
#     "lelbowpitch",  # 14
#     "lwristroll",  # 15


class CommandInterface(ABC):
    """Abstract base class for command input interfaces."""

    def __init__(self) -> None:
        self.robot_config = RobotConfig()
        self.joint_cmd: dict[str, float] = RobotConfig.home_positions
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @abstractmethod
    def _read_input(self) -> None:
        """Separate thread that reads input from the specific interface and updates command vector."""
        pass

    def start(self) -> None:
        """Start the input reading thread."""
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._read_input, daemon=True)
            if self._thread is not None:
                self._running = True
                self._thread.start()

    def stop(self) -> None:
        """Stop the input reading thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def reset_cmd(self) -> None:
        """Reset all commands to zero."""
        self.joint_cmd = {}

    def get_cmd(self) -> dict[str, float]:
        """Get current command vector per policy specification."""
        return self.joint_cmd
