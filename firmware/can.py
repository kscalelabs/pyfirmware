"""CAN communication and motor driver interfaces for actuators."""

import socket
import struct
import time
from typing import Any, Dict, Optional

from firmware.actuators import ActuatorConfig, FaultCode, Mux, RobotConfig


class CriticalFaultError(Exception):
    pass


class CANInterface:
    # Constants
    FRAME_FMT = "<IBBBB8s"
    FRAME_SIZE = struct.calcsize(FRAME_FMT)
    EFF = 0x8000_0000
    HOST_ID = 0xFD
    CAN_TIMEOUT = 0.001
    CANBUS_RANGE = range(0, 7)
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

    def __init__(self, robotcfg: RobotConfig, can_index: int) -> None:
        self.robotcfg = robotcfg
        self.can_index = can_index
        self.sock: Optional[socket.socket] = None
        self.pings_actuators = list[int]()
        self.actuators: dict[int, dict[str, Any]] = {}

        # Initialize socket and find actuators
        self._init_socket()
        self.find_actuators(can_index)

    def _init_socket(self) -> None:
        """Initialize CAN socket."""
        try:
            self.sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            if self.sock is None:
                raise Exception("Failed to create socket")
            self.sock.bind((f"can{self.can_index}",))
            self.sock.settimeout(self.CAN_TIMEOUT)
            print(f"✓ Initialized CAN{self.can_index}")
        except Exception as e:
            print(f"✗ Failed to initialize CAN{self.can_index}: {e}")
            raise

    def _build_and_send_can_frame(self, actuator_can_id: int, mux: int, payload: bytes = b"\x00" * 8) -> None:
        can_id = ((actuator_can_id & 0xFF) | (self.HOST_ID << 8) | ((mux & 0x1F) << 24)) | self.EFF
        self.sock.send(struct.pack(self.FRAME_FMT, can_id, 8 & 0xFF, 0, 0, 0, payload[:8]))

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

    def _receive_can_frame(self, mux: int) -> Optional[Dict[str, Any]]:
        try:
            while True:
                frame = self.sock.recv(self.FRAME_SIZE)
                parsed_frame = self._parse_can_frame(frame)

                self._check_for_faults(
                    self.CAN_ID_FAULT_CODES,
                    parsed_frame["fault_flags"],
                    parsed_frame["actuator_can_id"]
                )

                if parsed_frame["mux"] == Mux.FAULT_RESPONSE:
                    self._process_fault_response(parsed_frame["payload"], parsed_frame["actuator_can_id"])

                if parsed_frame["mux"] == Mux.FEEDBACK:
                    angle_be, ang_vel_be, torque_be, temp_be = struct.unpack(">HHHH", parsed_frame["payload"])
                    can_id = parsed_frame["actuator_can_id"]
                    angle_physical = self.robotcfg.actuators[can_id].can_to_physical_angle(angle_be)
                    angular_velocity_physical = self.robotcfg.actuators[can_id].can_to_physical_velocity(ang_vel_be)
                    torque_physical = self.robotcfg.actuators[can_id].can_to_physical_torque(torque_be)
                    temperature_physical = self.robotcfg.actuators[can_id].can_to_physical_temperature(temp_be)
                    name = self.robotcfg.actuators[can_id].name
                    actuator_state =  {
                        "name": name,
                        "actuator_can_id": parsed_frame["actuator_can_id"],
                        "fault_flags": parsed_frame["fault_flags"],
                        "angle": angle_physical,
                        "velocity": angular_velocity_physical,
                        "torque": torque_physical,
                        "temperature": temperature_physical,
                        "last_updated": time.perf_counter(),
                    }

                    self.actuators[can_id] = actuator_state

                if parsed_frame["mux"] == mux or mux is None:
                    return parsed_frame
        except Exception:
            return None

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

    def find_actuators(self, can_index: int) -> list[ActuatorConfig]:
        print(f"\033[1;36m🔍 Scanning CAN{can_index} for actuators...\033[0m")
        self._build_and_send_can_frame(0, Mux.PING)
        for actuator_id in self.ACTUATOR_RANGE:
            self._build_and_send_can_frame(actuator_id, Mux.PING)
            response = self._receive_can_frame(Mux.PING)
            if response is not None:
                found_id = response["actuator_can_id"]
                if found_id in self.robotcfg.actuators:
                    self.pings_actuators.append(found_id)

    def enable_motors(self) -> None:
        for actuator_id in self.pings_actuators:
            if self.sock is None:
                return
            self._build_and_send_can_frame(actuator_id, Mux.MOTOR_ENABLE)
            self._receive_can_frame(Mux.FEEDBACK)

    def disable_motors(self) -> None:
        for actuator_id in self.pings_actuators:
            self._build_and_send_can_frame(actuator_id, Mux.MOTOR_DISABLE)
            self._receive_can_frame(Mux.FEEDBACK)
            time.sleep(0.01)

    def get_actuator_feedback(self, timeout: float = 0.1) -> Dict[int, Dict[str, int]]:
        for actuator_id in self.pings_actuators:
            try:
                self._build_and_send_can_frame(actuator_id, Mux.FEEDBACK)
                time.sleep(0.00002)
            except Exception as e:
                print(f"\033[1;33mWARNING: Failed to send feedback request to {actuator_id}: {e}\033[0m")

        for _ in range(len(self.pings_actuators)):
            self._receive_can_frame(Mux.FEEDBACK)

        return self.actuators

    def set_pd_targets(self, actions: dict[int, float], scaling: float) -> None:
        for actuator_id in self.pings_actuators:
            if actuator_id in actions:
                try:
                    self._build_and_send_pd_command_frame(actuator_id, actions[actuator_id], scaling)
                except Exception as e:
                    print(f"\033[1;33mWARNING: Failed to send PD command to {actuator_id}: {e}\033[0m")

    def _build_and_send_pd_command_frame(
        self, actuator_can_id: int, angle: float, scaling: float
    ) -> None:
        assert 0.0 <= scaling <= 1.0
        config = self.robotcfg.actuators[actuator_can_id]
        raw_torque = int(config.physical_to_can_torque(0))
        raw_angle = int(config.physical_to_can_angle(angle))
        raw_ang_vel = int(config.physical_to_can_velocity(0))
        raw_kp = int(config.raw_kp * scaling)
        raw_kd = int(config.raw_kd * scaling)

        can_id = ((actuator_can_id & 0xFF) | (raw_torque << 8) | ((Mux.CONTROL & 0x1F) << 24)) | self.EFF
        payload = struct.pack(">HHHH", raw_angle, raw_ang_vel, raw_kp, raw_kd)
        self.sock.send(struct.pack(self.FRAME_FMT, can_id, 8 & 0xFF, 0, 0, 0, payload[:8]))

    def flush_can_bus_completely(self) -> int:
        while True:
            result = self._receive_can_frame(None)
            if result is None:
                break

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception as e:
                print(f"Error closing CAN{self.can_index} socket: {e}")
            finally:
                self.sock = None

