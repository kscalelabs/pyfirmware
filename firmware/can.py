"""CAN communication and motor driver interfaces for actuators."""

import socket
import struct
from typing import Any, Dict, Optional

from firmware.actuators import ActuatorConfig, FaultCode, Mux, RobotConfig


class CriticalFaultError(Exception):
    pass


class CANInterface:
    """Communication only."""

    # Constants
    FRAME_FMT = "<IBBBB8s"
    FRAME_SIZE = struct.calcsize(FRAME_FMT)
    EFF = 0x8000_0000
    HOST_ID = 0xFD
    CAN_TIMEOUT = 0.002
    ACTUATOR_RANGE = range(10, 50)
    # Fault codes
    MUX_0x15_FAULT_CODES = [
        FaultCode(0x01, True, "Motor Over-temperature (>145°C)"),
        FaultCode(0x02, True, "Driver Fault (DRV status)"),
        FaultCode(0x04, False, "Undervoltage (VBUS < 12V)"),
        FaultCode(0x08, False, "Overvoltage (VBUS > 60V)"),
        FaultCode(0x80, False, "Encoder Uncalibrated"),
        FaultCode(0x4000, True, "Stall/I²t Overload"),
    ]
    MUX_0x15_WARNING_CODES = [
        FaultCode(0x01, False, "Motor overtemperature warning (default 135°C)"),
    ]
    CAN_ID_FAULT_CODES = [
        FaultCode(0x20, False, "Uncalibrated"),
        FaultCode(0x10, False, "Gridlock overload fault"),
        FaultCode(0x08, False, "Magnetic coding fault"),
        FaultCode(0x04, True, "Overtemperature"),
        FaultCode(0x02, True, "Overcurrent"),
        FaultCode(0x01, False, "Undervoltage"),
    ]

    def __init__(self, robotcfg: RobotConfig) -> None:
        self.robotcfg = robotcfg
        self.sock: socket.socket = socket
        self.active_actuators: list[ActuatorConfig] = []

    def _build_can_frame(self, actuator_can_id: int, mux: int, payload: bytes = b"\x00" * 8) -> bytes:
        can_id = ((actuator_can_id & 0xFF) | (self.HOST_ID << 8) | ((mux & 0x1F) << 24)) | self.EFF
        return struct.pack(self.FRAME_FMT, can_id, 8 & 0xFF, 0, 0, 0, payload[:8])

    def _parse_can_frame(self, frame: bytes) -> Dict[str, Any]:
        if len(frame) != 16:
            raise ValueError("frame must be exactly 16 bytes")
        can_id, _length, _pad, _res0, _len8, payload = struct.unpack(self.FRAME_FMT, frame)
        host_id = (can_id >> 0) & 0xFF
        actuator_can_id = (can_id >> 8) & 0xFF
        mode_status = (can_id >> 22) & 0x03
        fault_flags = (can_id >> 16) & 0x3F
        mux = (can_id >> 24) & 0x1F
        return {
            "host_id": host_id,
            "actuator_can_id": actuator_can_id,
            "fault_flags": fault_flags,
            "mode_status": mode_status,
            "mux": mux,
            "payload": payload,
        }

    def _receive_can_frame(self, mux: int) -> Optional[Dict[str, int]]:
        """Recursively receive can frames until the mux is the expected value."""
        try:
            frame = self.sock.recv(self.FRAME_SIZE)
            parsed_frame = self._parse_can_frame(frame)
        except Exception:
            return None

        self._check_for_faults(self.CAN_ID_FAULT_CODES, parsed_frame["fault_flags"], parsed_frame["actuator_can_id"])
        if parsed_frame["mux"] != mux:
            print(f"\033[1;33mWARNING: unexpected mux 0x{parsed_frame['mux']:02X} in feedback response\033[0m")
            if parsed_frame["mux"] == Mux.FAULT_RESPONSE:
                self._process_fault_response(parsed_frame["payload"], parsed_frame["actuator_can_id"])
            return self._receive_can_frame(mux)  # call again recursively
        else:
            return parsed_frame

    def _check_for_faults(self, faults: list[FaultCode], fault_flags: int, actuator_can_id: int) -> None:
        for fault_code in faults:
            if fault_flags == fault_code.code:
                msg = f"Actuator {actuator_can_id}: {fault_code.description}"
                if fault_code.critical:
                    raise CriticalFaultError(f"\033[1;31mCRITICAL FAULT: {msg}\033[0m")
                print(f"\033[1;33mWARNING: {msg}\033[0m")

    def _process_fault_response(self, payload: bytes, actuator_can_id: int) -> None:
        fault_value, warning_value = struct.unpack("<II", payload)  # Little-endian uint32
        self._check_for_faults(self.MUX_0x15_FAULT_CODES, fault_value, actuator_can_id)
        self._check_for_faults(self.MUX_0x15_WARNING_CODES, warning_value, actuator_can_id)

    def find_actuators(self, can_index: int) -> None:
        print("\033[1;36m🔍 Scanning CAN buses for actuators...\033[0m")

        sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        try:
            sock.bind((f"can{can_index}",))
            sock.settimeout(self.CAN_TIMEOUT)
            sock.send(self._build_can_frame(0, Mux.PING))  # test message
        except Exception:
            return []

        print(f"Scanning bus {can_index}...")
        for actuator_id in self.ACTUATOR_RANGE:
            if actuator_id_response := self._ping_actuator(sock, actuator_id):
                found_id = actuator_id_response["actuator_can_id"]
                self.active_actuators.append(self.robotcfg.actuators[found_id])

        print(f"\033[1;34m{can_index}\033[0m: \033[1;35m{len(self.active_actuators)}\033[0m")
        return self.active_actuators

    def _ping_actuator(self, actuator_can_id: int) -> Optional[Dict[str, int]]:
        frame = self._build_can_frame(actuator_can_id, Mux.PING)
        self.sock.send(frame)
        return self._receive_can_frame(Mux.PING)

    def enable_motors(self) -> None:
        for actuator in self.active_actuators:
            self._enable_motor(actuator.can_id)

    def _enable_motor(self, actuator_can_id: int) -> None:
        frame = self._build_can_frame(actuator_can_id, Mux.MOTOR_ENABLE)
        self.socket.send(frame)
        _ = self._receive_can_frame(Mux.FEEDBACK)

    def get_actuator_feedback(self) -> Dict[int, Dict[str, int]]:
        """Send one message per bus; wait for all of them concurrently."""
        results: dict[int, dict[str, int]] = {}
        # Send requests
        for actuator_id in self.active_actuators:
                frame = self._build_can_frame(actuator_id, Mux.FEEDBACK)
                self.sock.send(frame)

            # Receive responses
        for _ in range(len(self.active_actuators)):
            parsed_frame = self._receive_can_frame(Mux.FEEDBACK)
            if parsed_frame is None:  # timeout
                print(f"\033[1;33mWARNING: [gaf] recv timeout actuator {actuator_id}\033[0m")
                continue
            result = self._parse_feedback_response(parsed_frame)
            actuator_id = result["actuator_can_id"]

            results[actuator_id] = result
        return results

    def _parse_feedback_response(self, response: Dict[str, Any]) -> Dict[str, int]:
        angle_be, ang_vel_be, torque_be, temp_be = struct.unpack(">HHHH", response["payload"])
        return {
            "host_id": response["host_id"],
            "actuator_can_id": response["actuator_can_id"],
            "fault_flags": response["fault_flags"],
            "angle_raw": angle_be,
            "angular_velocity_raw": ang_vel_be,
            "torque_raw": torque_be,
            "temperature_raw": temp_be,
        }

    def set_pd_targets(self, actions: dict[int, float], scaling: float) -> None:
        for actuator in self.active_actuators:
            if actuator.can_id in actions:
                frame = self._build_pd_command_frame(actuator.can_id, actions[actuator.can_id], scaling)
                self.sock.send(frame)

        # Receive all responses
        for _ in range(len(self.active_actuators)):
            parsed_frame = self._receive_can_frame(Mux.FEEDBACK)
            if parsed_frame is None:  # timeout
                print("\033[1;33mWARNING: [spdt] recv timeout\033[0m")

    def _build_pd_command_frame(
        self, actuator_can_id: int, angle: float, robotcfg: RobotConfig, scaling: float
    ) -> bytes:
        assert 0.0 <= scaling <= 1.0
        raw_torque = int(robotcfg.actuators[actuator_can_id].physical_to_can_torque(0))
        raw_angle = int(robotcfg.actuators[actuator_can_id].physical_to_can_angle(angle))
        raw_ang_vel = int(robotcfg.actuators[actuator_can_id].physical_to_can_velocity(0))
        raw_kp = int(robotcfg.actuators[actuator_can_id].raw_kp * scaling)
        raw_kd = int(robotcfg.actuators[actuator_can_id].raw_kd * scaling)

        can_id = ((actuator_can_id & 0xFF) | (raw_torque << 8) | ((Mux.CONTROL & 0x1F) << 24)) | self.EFF
        payload = struct.pack(">HHHH", raw_angle, raw_ang_vel, raw_kp, raw_kd)
        return struct.pack(self.FRAME_FMT, can_id, 8 & 0xFF, 0, 0, 0, payload[:8])

    def flush_can_bus(self) -> None:
        """Try to drain 1 message from each CAN bus.

        Actuators sometimes send late or extra messages that we need to get rid of.
        """
        result = self._receive_can_frame(Mux.FEEDBACK)
        return result

    def close(self) -> None:
        """Close all CAN sockets."""
        try:
            self.sock.close()
        except Exception as e:
            print(f"Error closing socket: {e}")

