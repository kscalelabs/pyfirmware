"""UDP-based command input implementation."""

import json
import socket
import time
from typing import Optional

from firmware.commands.command_interface import CMD_NAMES, CommandInterface


class UDPListener(CommandInterface):
    """Listens for UDP commands and updates the command vector."""

    def __init__(self, command_names: list[str], joint_names: list[str], port: int = 10000, host: str = "0.0.0.0") -> None:
        print(f"Using UDP input on port {port} for commands: {command_names}")
        super().__init__(policy_command_names=command_names)
        self.joint_names = joint_names

        self.port = port
        self.host = host
        self.sock: Optional[socket.socket] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(0.1)

        self.start()

    def _read_input(self) -> None:
        """Read UDP packets and update command vector."""
        while self._running:
            if self.sock:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    command_data = json.loads(data.decode("utf-8"))

                    if command_data.get("type") == "reset":
                        self.reset_cmd()
                        continue

                    payload = command_data.get("commands", command_data)
                    for name, value in payload.items():
                        if name in self.cmd:
                            self.cmd[str(name).lower()] = float(value)
                        elif name in self.joint_names:
                            self.joint_cmd[name] = float(value)
                        else:
                            print(f"Warning: Command name '{name}' not supported by policy")

                except socket.timeout:
                    continue
                except Exception:
                    continue
            else:
                time.sleep(0.1)

    def stop(self) -> None:
        """Stop UDP listening."""
        super().stop()
        if self.sock:
            self.sock.close()
            self.sock = None


if __name__ == "__main__":
    print("Starting UDP listener on port 10000...")
    print("Send JSON commands like: {'commands': [0.1, -0.05, 0.0]} or {'type': 'reset'}")
    print("Press Ctrl+C to stop")

    listener = UDPListener(command_names=CMD_NAMES, port=10000)

    try:
        while True:
            cmd = listener.get_cmd()
            print(f"Current command: {cmd}")
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nStopping UDP listener...")
        listener.stop()
