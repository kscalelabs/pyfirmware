"""Keyboard command input implementation."""

import atexit
import select
import sys
import termios
import tty
from typing import List

from firmware.commands.command_interface import CommandInterface


class Keyboard(CommandInterface):
    """Tracks keyboard presses to update the command vector."""

    def __init__(self, command_names: List[str]) -> None:
        super().__init__(policy_command_names=command_names)

        # Set up stdin for raw input
        self._fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        atexit.register(lambda: termios.tcsetattr(self._fd, termios.TCSADRAIN, old_settings))

        # Start keyboard reading
        self.start()

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

                # clamp
                self.cmd = {k: max(-0.3, min(0.3, v)) for k, v in self.cmd.items()}

            except (IOError, EOFError):
                continue
