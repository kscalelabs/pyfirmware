import atexit
import select
import sys
import termios
import tty

from commands.command_interface import CommandInterface


class Keyboard(CommandInterface):
    """Tracks keyboard presses to update the command vector."""

    def __init__(self) -> None:
        super().__init__()

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
            # Use select to check for input with a timeout
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not rlist:
                continue

            try:
                ch = sys.stdin.read(1).lower()

                # base controls
                if ch == "0":
                    self.reset_cmd()
                elif ch == "w":
                    self.cmd[0] += 0.1
                elif ch == "s":
                    self.cmd[0] -= 0.1
                elif ch == "a":
                    self.cmd[1] += 0.1
                elif ch == "d":
                    self.cmd[1] -= 0.1
                elif ch == "q":
                    self.cmd[2] += 0.1
                elif ch == "e":
                    self.cmd[2] -= 0.1

                # base pose
                elif ch == "=":
                    self.cmd[3] += 0.05
                elif ch == "-":
                    self.cmd[3] -= 0.05
                elif ch == "r":
                    self.cmd[4] += 0.1
                elif ch == "f":
                    self.cmd[4] -= 0.1
                elif ch == "t":
                    self.cmd[5] += 0.1
                elif ch == "g":
                    self.cmd[5] -= 0.1

                # clamp
                self.cmd = [max(-0.3, min(0.3, cmd)) for cmd in self.cmd]

            except (IOError, EOFError):
                continue


if __name__ == "__main__":
    kb = Keyboard()

    import time

    while True:
        print(kb.get_cmd())
        time.sleep(0.1)
