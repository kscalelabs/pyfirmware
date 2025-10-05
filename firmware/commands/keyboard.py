"""Keyboard command input implementation."""

import atexit
import select
import sys
import termios
import tty
from typing import List

from firmware.commands.command_interface import CommandInterface
from firmware.commands.motions import MOTIONS


class Keyboard(CommandInterface):
    """Tracks keyboard presses to update the command vector."""

    def __init__(self, command_names: List[str]) -> None:
        super().__init__(policy_command_names=command_names)
        self.active_motion = None

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
        self.active_motion = MOTIONS[motion_name](dt=0.02) #TODO hard coded

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
            

            except (IOError, EOFError):
                continue


    def get_cmd(self) -> List[float]:
        """Get current command vector per policy specification."""
        if self.active_motion:
            commands = self.active_motion.get_next_motion_frame()
            if commands is None:
                self.active_motion = None
                return super().get_cmd()
            else:
                # only get commands the policy supports and fill the rest with zeros
                return [commands[name] if name in commands else 0.0 for name in self.policy_command_names]
        return super().get_cmd()