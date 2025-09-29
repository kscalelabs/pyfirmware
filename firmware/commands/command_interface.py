import threading
from abc import ABC, abstractmethod
from typing import List


class CommandInterface(ABC):
    """Abstract base class for command input interfaces."""

    def __init__(self, length: int = 16):
        self.cmd = [0.0] * length
        self.length = length
        self._running = True
        self._thread = None

    @abstractmethod
    def _read_input(self) -> None:
        """Read input from the specific interface and update command vector in a separate thread."""
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
        self.cmd = [0.0] * self.length

    def get_cmd(self) -> List[float]:
        """Get current command vector."""
        return self.cmd

    def __del__(self):
        """Cleanup on destruction."""
        self.stop()
