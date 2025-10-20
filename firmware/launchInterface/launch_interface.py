"""Base interface for launching robot control workflows."""

import sys
from abc import ABC, abstractmethod
from typing import Optional

MAX_ANGLE = 2.0

class LaunchInterface(ABC):
    """Abstract interface for launch UIs (keyboard, websocket, etc.)."""

    @abstractmethod
    def get_command_source(self) -> str:
        """Return the command source type, e.g. "keyboard" or "udp"."""
        raise NotImplementedError

    @abstractmethod
    def ask_motor_permission(self, robot_devices: dict) -> bool:
        """Ask permission to enable motors. Return True to proceed, False to abort."""
        raise NotImplementedError

    @abstractmethod
    def launch_policy_permission(self) -> bool:
        """Ask permission to start the policy. Return True to proceed, False to abort."""
        raise NotImplementedError

    @abstractmethod
    def get_kinfer_path(self, policy_dir_path: str) -> Optional[str]:
        """Return the selected .kinfer path or None if cancelled/invalid."""
        raise NotImplementedError

    def enable_motors_sanity_check(self, joint_data_dict: dict) -> bool:
        """Check if actuators are safe to enable."""
        if any(abs(data["angle"]) > MAX_ANGLE for data in joint_data_dict.values()):
            print(
                f"\033[1;31mERROR: Actuator angles too far from zero (max={MAX_ANGLE:.1f} rad) - "
                f"move joints closer to home position\033[0m"
            )
            sys.exit(1)
        return True

    def stop(self) -> None:
        """Cleanup/teardown resources owned by the implementation."""
        return
