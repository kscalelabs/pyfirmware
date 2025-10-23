"""CAN communication and motor driver interfaces for actuators."""

import socket
import struct
import time
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
        """Initialize CAN interface for a specific bus.

        Args:
            robotcfg: Robot configuration containing actuator specs
            can_index: CAN bus index (e.g., 0 for can0)
        """
        self.robotcfg = robotcfg
        self.can_index = can_index
        self.sock: Optional[socket.socket] = None
        self.active_actuators: list[ActuatorConfig] = []

        # Initialize socket and find actuators
        self._init_socket()
        self.find_actuators(can_index)

    def _init_socket(self) -> None:
        """Initialize CAN socket."""
        try:
            self.sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            self.sock.bind((f"can{self.can_index}",))
            self.sock.settimeout(self.CAN_TIMEOUT)
            print(f"✓ Initialized CAN{self.can_index}")
        except Exception as e:
            print(f"✗ Failed to initialize CAN{self.can_index}: {e}")
            raise

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

    def _receive_can_frame(self, mux: int) -> Optional[Dict[str, Any]]:
        """Recursively receive can frames until the mux is the expected value."""
        if self.sock is None:
            return None

        try:
            frame = self.sock.recv(self.FRAME_SIZE)
            parsed_frame = self._parse_can_frame(frame)
        except Exception:
            return None

        self._check_for_faults(
            self.CAN_ID_FAULT_CODES,
            parsed_frame["fault_flags"],
            parsed_frame["actuator_can_id"]
        )

        if parsed_frame["mux"] != mux:
            print(f"\033[1;33mWARNING: unexpected mux 0x{parsed_frame['mux']:02X} in feedback response\033[0m")
            if parsed_frame["mux"] == Mux.FAULT_RESPONSE:
                self._process_fault_response(parsed_frame["payload"], parsed_frame["actuator_can_id"])
            return self._receive_can_frame(mux)  # Recursive retry

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

    def find_actuators(self, can_index: int) -> list[ActuatorConfig]:
        """Scan this CAN bus for actuators."""
        print(f"\033[1;36m🔍 Scanning CAN{can_index} for actuators...\033[0m")

        if self.sock is None:
            return []

        # Test bus with ping
        try:
            self.sock.send(self._build_can_frame(0, Mux.PING))
        except Exception as e:
            print(f"✗ CAN{can_index} not responsive: {e}")
            return []

        for actuator_id in self.ACTUATOR_RANGE:
            if response := self._ping_actuator(actuator_id):
                found_id = response["actuator_can_id"]
                if found_id in self.robotcfg.actuators:
                    self.active_actuators.append(self.robotcfg.actuators[found_id])

        print(f"\033[1;32m✓ CAN{can_index}: Found {len(self.active_actuators)} actuators\033[0m")
        return self.active_actuators

    def _ping_actuator(self, actuator_can_id: int) -> Optional[Dict[str, Any]]:
        """Ping a specific actuator."""
        if self.sock is None:
            return None
        frame = self._build_can_frame(actuator_can_id, Mux.PING)
        self.sock.send(frame)
        return self._receive_can_frame(Mux.PING)

    def enable_motors(self) -> None:
        """Enable all motors on this bus."""
        for actuator in self.active_actuators:
            self._enable_motor(actuator.can_id)

    def _enable_motor(self, actuator_can_id: int) -> None:
        """Enable a single motor."""
        if self.sock is None:
            return
        frame = self._build_can_frame(actuator_can_id, Mux.MOTOR_ENABLE)
        self.sock.send(frame)
        _ = self._receive_can_frame(Mux.FEEDBACK)

    def disable_motors(self) -> None:
        """Disable all motors on this bus."""
        for actuator in self.active_actuators:
            frame = self._build_can_frame(actuator.can_id, Mux.MOTOR_DISABLE)
            self.sock.send(frame)
            time.sleep(0.01)

    def get_actuator_feedback(self, timeout: float = 0.1) -> Dict[int, Dict[str, int]]:
        """Get feedback from all actuators on this bus.

        Args:
            timeout: Maximum time to wait for all responses in seconds

        Returns:
            Dictionary mapping actuator_id to feedback data
        """
        t_start = time.perf_counter()
        results: Dict[int, Dict[str, int]] = {}

        if self.sock is None:
            return results

        # Send all feedback requests
        for actuator in self.active_actuators:
            try:
                frame = self._build_can_frame(actuator.can_id, Mux.FEEDBACK)
                self.sock.send(frame)
            except Exception as e:
                print(f"\033[1;33mWARNING: Failed to send feedback request to {actuator.can_id}: {e}\033[0m")

        # Receive all responses
        for _ in range(len(self.active_actuators)):
            parsed_frame = self._receive_can_frame(Mux.FEEDBACK)
            if parsed_frame is None:
                # Timeout - continue to try receiving from other actuators
                continue

            result = self._parse_feedback_response(parsed_frame)
            actuator_id = result["actuator_can_id"]
            results[actuator_id] = result

        # Check if we got all responses
        missing = len(self.active_actuators) - len(results)
        if missing > 0:
            print(f"\033[1;33mWARNING: CAN{self.can_index} missing {missing} responses\033[0m")

        t_end = time.perf_counter()
        total_time_us = (t_end - t_start) * 1e6
        print(f"\033[1;36m✓ CAN{self.can_index} feedback: {len(results)} actuators in {total_time_us:.0f}μs\033[0m")

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
        """Send PD control commands to actuators (non-blocking).

        Args:
            actions: Dictionary mapping actuator_id to target angle
            scaling: PD gain scaling factor (0.0 to 1.0)
        """
        if self.sock is None:
            return

        # Send all commands without waiting for responses
        for actuator in self.active_actuators:
            actuator_id = actuator.can_id
            if actuator_id in actions:
                try:
                    frame = self._build_pd_command_frame(actuator_id, actions[actuator_id], scaling)
                    self.sock.send(frame)
                except Exception as e:
                    print(f"\033[1;33mWARNING: Failed to send PD command to {actuator_id}: {e}\033[0m")


    def _build_pd_command_frame(
        self, actuator_can_id: int, angle: float, scaling: float
    ) -> bytes:
        assert 0.0 <= scaling <= 1.0
        raw_torque = int(self.robotcfg.actuators[actuator_can_id].physical_to_can_torque(0))
        raw_angle = int(self.robotcfg.actuators[actuator_can_id].physical_to_can_angle(angle))
        raw_ang_vel = int(self.robotcfg.actuators[actuator_can_id].physical_to_can_velocity(0))
        raw_kp = int(self.robotcfg.actuators[actuator_can_id].raw_kp * scaling)
        raw_kd = int(self.robotcfg.actuators[actuator_can_id].raw_kd * scaling)

        can_id = ((actuator_can_id & 0xFF) | (raw_torque << 8) | ((Mux.CONTROL & 0x1F) << 24)) | self.EFF
        payload = struct.pack(">HHHH", raw_angle, raw_ang_vel, raw_kp, raw_kd)
        return struct.pack(self.FRAME_FMT, can_id, 8 & 0xFF, 0, 0, 0, payload[:8])

    def flush_can_bus_completely(self) -> int:
        """Drain all pending messages from the CAN bus.

        Returns:
            Number of messages flushed
        """
        if self.sock is None:
            return 0

        count = 0
        while True:
            result = self._receive_can_frame(Mux.FEEDBACK)
            if result is None:  # Timeout means bus is empty
                break
            count += 1

        if count > 0:
            print(f"\033[1;32mFlushed {count} messages from CAN{self.can_index}\033[0m")

        return count

    def close(self) -> None:
        """Close socket and cleanup resources."""
        # Close socket
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception as e:
                print(f"Error closing CAN{self.can_index} socket: {e}")
            finally:
                self.sock = None

        self.active_actuators.clear()

