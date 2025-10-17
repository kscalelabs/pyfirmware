"""Keyboard command input implementation."""

import atexit
import math
import select
import sys
import termios
import tty
from typing import Any, List

from kmotions.motions import MOTIONS

from firmware.commands.command_interface import CommandInterface

ACTION_SPACE_JOINT_LIMITS: dict[str, tuple[float, float]] = {
    "rshoulderpitch": (-3.490658, 1.047198),
    "rshoulderroll": (-1.658063 - math.radians(10.0), 0.436332 + math.radians(10.0)),
    "rshoulderyaw": (-1.671886, 1.671886),
    "relbowpitch": (0.0 - math.radians(90.0), 2.478368 + math.radians(90.0)),
    "rwristroll": (-1.37881, 1.37881),
    "lshoulderpitch": (-1.047198, 3.490658),
    "lshoulderroll": (-0.436332 - math.radians(10.0), 1.658063 + math.radians(10.0)),
    "lshoulderyaw": (-1.671886, 1.671886),
    "lelbowpitch": (-2.478368 - math.radians(90.0), 0.0 + math.radians(90.0)),
    "lwristroll": (-1.37881, 1.37881),
}


def clamp(name: str, value: float) -> float:
    if name in ACTION_SPACE_JOINT_LIMITS:
        return min(max(value, ACTION_SPACE_JOINT_LIMITS[name][0]), ACTION_SPACE_JOINT_LIMITS[name][1])
    return value


class Keyboard(CommandInterface):
    """Tracks keyboard presses to update the command vector."""

    # TODO assert cmd names and fall back to zeros?
    # TODO begone joint limits

    def __init__(self, command_names: List[str]) -> None:
        super().__init__(policy_command_names=command_names)
        self.active_motion: Any = None

        # Set up stdin for raw input
        self._fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        atexit.register(lambda: termios.tcsetattr(self._fd, termios.TCSADRAIN, old_settings))

        # Start keyboard reading
        self.start()

    def set_motion(self, motion_name: str) -> None:
        """Set the active motion."""
        print(f"Setting active motion to {motion_name}")
        self.active_motion = MOTIONS[motion_name](dt=0.02)  # type: ignore[call-arg]  # TODO hard coded

    def _read_input(self) -> None:
        """Read keyboard input and update command vector."""
        while self._running:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not rlist:
                continue

            try:
                ch = sys.stdin.read(1).lower()

                # base controls
                if ch == "0":
                    self.reset_cmd()
                elif ch == "w":
                    self.cmd["xvel"] += 0.1
                elif ch == "s":
                    self.cmd["xvel"] -= 0.1
                elif ch == "a":
                    self.cmd["yvel"] += 0.1
                elif ch == "d":
                    self.cmd["yvel"] -= 0.1
                elif ch == "q":
                    self.cmd["yawrate"] += 0.1
                elif ch == "e":
                    self.cmd["yawrate"] -= 0.1

                # base pose
                elif ch == "=":
                    self.cmd["baseheight"] += 0.05
                elif ch == "-":
                    self.cmd["baseheight"] -= 0.05
                elif ch == "r":
                    self.cmd["baseroll"] += 0.1
                elif ch == "f":
                    self.cmd["baseroll"] -= 0.1
                elif ch == "t":
                    self.cmd["basepitch"] += 0.1
                elif ch == "g":
                    self.cmd["basepitch"] -= 0.1

                # Clamp velocity commands to ±0.8, other commands to ±0.3
                for cmd_name, value in self.cmd.items():
                    if cmd_name in ["xvel", "yvel", "yawrate"]:
                        self.cmd[cmd_name] = max(-0.8, min(0.8, value))
                    else:
                        self.cmd[cmd_name] = max(-0.3, min(0.3, value))

                # motion controls
                if ch == "z":
                    self.set_motion("wave")
                elif ch == "x":
                    self.set_motion("salute")
                elif ch == "c":
                    self.set_motion("come_at_me")
                elif ch == "v":
                    self.set_motion("boxing_guard_hold")
                elif ch == "b":
                    self.set_motion("boxing_left_punch")
                elif ch == "n":
                    self.set_motion("boxing_right_punch")
                elif ch == "i":
                    self.set_motion("cone")

            except (IOError, EOFError):
                continue

    def get_cmd(self) -> List[float]:
        """Get current command vector per policy specification."""
        if self.active_motion:
            commands = self.active_motion.get_next_motion_frame()
            if commands:
                # only get commands the policy supports and fill the rest with zeros
                policy_commands = {name: commands.get(name, 0.0) for name in self.policy_command_names}
                clamped_commands = {name: clamp(name, policy_commands[name]) for name in self.policy_command_names}
                return {name: v for name, v in clamped_commands.items()}, {}
            else:
                self.active_motion = None
                self.reset_cmd()
        return super().get_cmd()
