import atexit
import select
import sys
import termios
import threading
import tty


class Keyboard:
    """Tracks keyboard presses to update the command vector."""

    def __init__(self) -> None:
        self._reset_cmd()
        
        # Set up stdin for raw input
        self._fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        atexit.register(lambda: termios.tcsetattr(self._fd, termios.TCSADRAIN, old_settings))

        # Start keyboard reading thread
        self._running = True
        self._thread = threading.Thread(target=self._read_keyboard, daemon=True)
        self._thread.start()

    def _reset_cmd(self) -> None:
        self.cmd = [0.0] * 16

    def _read_keyboard(self) -> None:
        while self._running:
            # Use select to check for input with a timeout
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not rlist:
                continue

            try:
                ch = sys.stdin.read(1).lower()

                # base controls
                if ch == '0':
                    self._reset_cmd()
                if ch == 'w':
                    self.cmd[0] += 0.1
                if ch == 's':
                    self.cmd[0] -= 0.1
                if ch == 'a':
                    self.cmd[1] += 0.1
                if ch == 'd':
                    self.cmd[1] -= 0.1
                if ch == 'q':
                    self.cmd[2] += 0.1
                if ch == 'e':
                    self.cmd[2] -= 0.1

                # base pose
                if ch == '=':
                    self.cmd[3] += 0.05
                if ch == '-':
                    self.cmd[3] -= 0.05
                if ch == 'r':
                    self.cmd[4] += 0.1
                if ch == 'f':
                    self.cmd[4] -= 0.1
                if ch == 't':
                    self.cmd[5] += 0.1
                if ch == 'g':
                    self.cmd[5] -= 0.1

                # diy clamp
                self.cmd = [max(-0.3, min(0.3, cmd)) for cmd in self.cmd]

            except (IOError, EOFError):
                continue

    def get_cmd(self) -> list[float]:
        return self.cmd


if __name__ == "__main__":
    kb = Keyboard()

    import time
    while True:
        print(kb.get_cmd())
        time.sleep(0.1)

