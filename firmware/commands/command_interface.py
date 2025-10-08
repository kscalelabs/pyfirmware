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
    "rshoulderroll",  # 22
    "rshoulderyaw",  # 23
    "relbowpitch",  # 24
    "rwristroll",  # 25
    "rgripper",  # 26
    "lshoulderpitch",  # 11
    "lshoulderroll",  # 12
    "lshoulderyaw",  # 13
    "lelbowpitch",  # 14
    "lwristroll",  # 15
    "lgripper",  # 16
]


class CommandInterface(ABC):
    """Abstract base class for command input interfaces."""

    def __init__(self, policy_command_names: List[str]) -> None:
        self.cmd = {cmd: 0.0 for cmd in CMD_NAMES}
        self.policy_command_names = [name.lower() for name in policy_command_names]
        for name in self.policy_command_names:
            if name not in CMD_NAMES:
                print(f"Warning: Policy command name '{name}' not supported by firmware")

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
        return [self.cmd.get(name, 0.0) for name in self.policy_command_names]

    def __del__(self) -> None:
        """Cleanup on destruction."""
        self.stop()
