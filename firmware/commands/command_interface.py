"""Abstract interface for command input sources (keyboard, UDP, etc.)."""

import threading
from abc import ABC, abstractmethod
from typing import List


CMD_NAMES = [
    "xvel",
    "yvel",
    "yawrate",
    "baseheight",
    "baseroll",
    "basepitch", 
    "rshoulderpitch",  # 21
    "rshoulderroll",   # 22
    "relebowpitch",    # 24
    "relebowroll",     # 23
    "rwristroll",      # 25
    "rwristgripper",   # 26
    "lshoulderpitch",  # 11
    "lshoulderroll",   # 12
    "lelebowpitch",    # 14
    "lelebowroll",     # 13
    "lwristroll",      # 15
    "lwristgripper",   # 16
]


class CommandInterface(ABC):
    """Abstract base class for command input interfaces."""

    def __init__(self, policy_command_names: List[str]) -> None:
        self.cmd = {cmd: 0.0 for cmd in CMD_NAMES}            
        self.policy_command_names = [name.lower() for name in policy_command_names]
        for name in self.policy_command_names:
            assert name in CMD_NAMES, f"Policy command name '{name}' not found in CMD_NAMES"

        self._running = True
        self._thread = None

    @abstractmethod
    def _read_input(self) -> None:
        """Separate thread that reads input from the specific interface and updates command vector."""
        pass

    def start(self) -> None:
        """Start the input reading thread."""
        if self._thread is None or not self._thread.is_alive():
            self._running = True
            self._thread = threading.Thread(target=self._read_input, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the input reading thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def reset_cmd(self) -> None:
        """Reset all commands to zero."""
        self.cmd = {cmd: 0.0 for cmd in self.cmd.keys()}

    def get_cmd(self) -> List[float]:
        """Get current command vector per policy specification."""
        return [self.cmd[name] for name in self.policy_command_names]

    def __del__(self) -> None:
        """Cleanup on destruction."""
        self.stop()
