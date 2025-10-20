"""Abstract interface for command input sources (keyboard, UDP, etc.)."""

import threading
from abc import ABC, abstractmethod
from typing import Optional

from firmware.actuators import RobotConfig


class CommandInterface(ABC):
    """Abstract base class for command input interfaces."""

    def __init__(self, policy_command_names: list[str]) -> None:
        self.policy_command_names = policy_command_names
        self.cmd = {cmd: 0.0 for cmd in policy_command_names}
        self.last_cmd: dict[str, float] = {}
        self.max_delta = 0.05
        self.joint_limits = {
            actuator.full_name: (actuator.joint_limit_min, actuator.joint_limit_max)
            for actuator in RobotConfig().actuators.values()
        }

        print("\nPolicy Command Names Supported")
        print("-" * 30)
        for i, cmd_name in enumerate(policy_command_names, 1):
            print(f"{i:2d}. {cmd_name:<20}")
        print("-" * 30 + "\n")

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
        self.cmd = {cmd_name: 0.0 for cmd_name in self.policy_command_names}
        self.last_cmd = {}

    def get_cmd(self) -> tuple[dict[str, float], dict[str, float]]:
        """Get new commands that are clamped for safety.

        - all commands clamped to max_delta from last command.
        - joint commands clamped to joint limits
        """
        clamped_cmd = {}
        for name, value in self.cmd.items():
            # clamp to max_delta from last command
            last_value = self.last_cmd.get(name, 0)
            clamped_value = max(last_value - self.max_delta, min(last_value + self.max_delta, value))

            # clamp to joint limits
            if name in self.joint_limits:
                clamped_value = max(self.joint_limits[name][0], min(self.joint_limits[name][1], clamped_value))

            clamped_cmd[name] = clamped_value
        self.last_cmd = clamped_cmd.copy()

        policy_cmd = {name: clamped_cmd[name] for name in self.policy_command_names}
        joint_cmd = {name: clamped_cmd[name] for name in clamped_cmd if name not in self.policy_command_names}

        return policy_cmd, joint_cmd
