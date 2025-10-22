"""Base interface for launching robot control workflows."""

from abc import ABC, abstractmethod
from typing import Optional


class LaunchInterface(ABC):
    @abstractmethod
    def get_command_source(self) -> str:
        """Return the command source type, e.g. "keyboard" or "udp"."""
        raise NotImplementedError

    @abstractmethod
    def ask_motor_permission(self, robot_devices: dict) -> bool:
        """Ask permission to enable motors. Return True to proceed, False to abort."""
        raise NotImplementedError

    @abstractmethod
    def launch_policy_permission(self, policy_name: str) -> bool:
        """Ask permission to start the policy. Return True to proceed, False to abort."""
        raise NotImplementedError

    @abstractmethod
    def get_kinfer_path(self, policy_dir_path: str) -> Optional[str]:
        """Return the selected .kinfer path or None if cancelled/invalid."""
        raise NotImplementedError

    def stop(self) -> None:
        """Cleanup/teardown resources owned by the implementation."""
        return
