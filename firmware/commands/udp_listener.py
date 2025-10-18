"""UDP-based command input implementation."""

import json
import socket
import time
from typing import Optional

from firmware.commands.command_interface import CommandInterface


class UDPListener(CommandInterface):
    """Listens for UDP commands and updates the command vector."""

    def __init__(
        self, port: int = 10000, host: str = "0.0.0.0"
    ) -> None:
        print(f"Using UDP input on port {port} for commands")
        super().__init__()
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
                    self.joint_cmd = self.command_to_actuator(payload)

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


    def command_to_actuator(self, command: dict[str, float]) -> dict[int, float]:
        mapping = {
            "rshoulderpitch": "dof_right_shoulder_pitch_03",
            "rshoulderroll": "dof_right_shoulder_roll_03",
            "rshoulderyaw": "dof_right_shoulder_yaw_02",
            "relbowpitch": "dof_right_elbow_02",
            "rwristroll": "dof_right_wrist_00",
            "rgripper": "dof_right_gripper_00",
            "lshoulderpitch": "dof_left_shoulder_pitch_03",
            "lshoulderroll": "dof_left_shoulder_roll_03",
            "lshoulderyaw": "dof_left_shoulder_yaw_02",
            "rshoulderyaw": "dof_right_shoulder_yaw_02",
            "relbowpitch": "dof_right_elbow_pitch_02",
            "rwristroll": "dof_right_wrist_00",
            "rgripper": "dof_right_gripper_00",
        }

        answer = dict()
        for name, angle in command.items():
            if name in mapping:
                answer[mapping[name]] = angle
        return answer
