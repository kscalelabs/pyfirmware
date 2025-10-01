"""UDP-based command input implementation."""

import json
import math
import socket

from firmware.commands.command_interface import CommandInterface


class UDPListener(CommandInterface):
    """Listens for UDP commands and updates the command vector."""

    def __init__(self, length: int = 16, port: int = 10000, host: str = "0.0.0.0") -> None:
        print(f"Using UDP input on port {port} ({length}-element commands)")
        super().__init__(length)
        self.port = port
        self.host = host
        self.sock = None

        if length == 18:
            self.cmd = [
                0.0,  # XVel
                0.0,  # YVel
                0.0,  # YawRate
                0.0,  # BaseHeight
                0.0,  # BaseRoll
                0.0,  # BasePitch
                0.0,  # RShoulderPitch (21)
                math.radians(-10.0),  # RShoulderRoll (22)
                0.0,  # RElbowPitch (24)
                math.radians(90.0),  # RElbowRoll (23)
                0.0,  # RWristRoll (25)
                math.radians(-8.0),  # RWristGripper (26)
                0.0,  # LShoulderPitch (11)
                math.radians(10.0),  # LShoulderRoll (12)
                0.0,  # LElbowPitch (14)
                math.radians(-90.0),  # LElbowRoll (13)
                0.0,  # LWristRoll (15)
                math.radians(-25.0),  # LWristGripper (16)
            ]
        else:
            self.default_cmd = [
                0.0,  # XVel
                0.0,  # YVel
                0.0,  # YawRate
                0.0,  # BaseHeight
                0.0,  # BaseRoll
                0.0,  # BasePitch
                0.0,  # RShoulderPitch (21)
                math.radians(-10.0),  # RShoulderRoll (22)
                0.0,  # RElbowPitch (24)
                math.radians(90.0),  # RElbowRoll (23)
                0.0,  # RWristRoll (25)
                0.0,  # LShoulderPitch (11)
                math.radians(10.0),  # LShoulderRoll (12)
                0.0,  # LElbowPitch (14)
                math.radians(-90.0),  # LElbowRoll (13)
                0.0,  # LWristRoll (15)
            ]
            self.cmd = self.default_cmd

        self.start()

    def _read_input(self) -> None:
        """Read UDP packets and update command vector."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.host, self.port))
            self.sock.settimeout(0.1)

            while self._running:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    command_data = json.loads(data.decode("utf-8"))

                    if command_data.get("type") == "reset":
                        self.reset_cmd()
                    elif self.length == 18:
                        self.cmd = command_data.get(
                            "commands", self.cmd
                        )  # self.cmd[index] = max(-0.3, min(0.3, self.cmd[index]))
                    else:
                        # Use index-based updates for other lengths
                        updates = command_data.get("commands", {})
                        for index_str, value in updates.items():
                            index = int(index_str)
                            if 0 <= index < self.length:
                                self.cmd[index] = float(value)

                except socket.timeout:
                    continue
                except Exception:
                    continue

        except Exception:
            pass
        finally:
            if self.sock:
                self.sock.close()

    def stop(self) -> None:
        """Stop UDP listening."""
        super().stop()
        if self.sock:
            self.sock.close()
            self.sock = None


if __name__ == "__main__":
    print("Starting UDP listener on port 10000...")
    print("Send JSON commands like:")
    print('  For 16-element: {"commands": {"0": 0.1, "1": -0.05}}')
    print('  For 18-element: {"XVel": 0.1, "YVel": -0.05, "YawRate": 0.0, ...}')
    print('  Reset: {"type": "reset"}')
    print("Press Ctrl+C to stop")

    listener = UDPListener(length=18, port=10000)

    try:
        while True:
            cmd = listener.get_cmd()
            print(f"Current command: {cmd}")
            import time

            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping UDP listener...")
        listener.stop()
