"""CAN communication and motor driver interfaces for actuators."""

import math
import select
import socket
import struct
import sys
import time
from typing import Dict

from firmware.actuators import FaultCode, Mux, RobotConfig


class CriticalFaultError(Exception):
    pass


class CANInterface:
    """Communication only."""

    def __init__(self) -> None:
        self.FRAME_FMT = "<IBBBB8s"  # <I = little-endian u32; 4B = len, pad, res0, len8_dlc; 8s = 8 data bytes
        self.FRAME_SIZE = struct.calcsize(self.FRAME_FMT)
        self.EFF = 0x8000_0000
        self.host_id = 0xFD
        self.canbus_range = range(0, 7)
        self.actuator_range = range(10, 50)

        # fault codes
        self.MUX_0x15_FAULT_CODES = [
            FaultCode(0x01, True, "Motor Over-temperature (>145°C)"),
            FaultCode(0x02, True, "Driver Fault (DRV status)"),
            FaultCode(0x04, False, "Undervoltage (VBUS < 12V)"),
            FaultCode(0x08, False, "Overvoltage (VBUS > 60V)"),
            FaultCode(0x80, False, "Encoder Uncalibrated"),
            FaultCode(0x4000, True, "Stall/I²t Overload"),
        ]
        self.MUX_0x15_WARNING_CODES = [
            FaultCode(0x01, False, "Motor overtemperature warning (default 135°C)"),
        ]
        self.CAN_ID_FAULT_CODES = [
            FaultCode(0x20, False, "Uncalibrated"),
            FaultCode(0x10, False, "Gridlock overload fault"),
            FaultCode(0x08, False, "Magnetic coding fault"),
            FaultCode(0x04, True, "Overtemperature"),
            FaultCode(0x02, True, "Overcurrent"),
            FaultCode(0x01, False, "Undervoltage"),
        ]

        self.sockets = {}
        self.actuators = {}
        self._find_actuators()
        self.missing_responses = {sock: [] for sock in self.sockets.values()}

    def _build_can_frame(self, actuator_can_id: int, mux: int, payload: bytes = b"\x00" * 8) -> bytes:
        can_id = ((actuator_can_id & 0xFF) | ((self.host_id) << 8) | ((mux & 0x1F) << 24)) | self.EFF
        return struct.pack(self.FRAME_FMT, can_id, 8 & 0xFF, 0, 0, 0, payload[:8])

    def _parse_can_frame(self, frame: bytes) -> Dict[str, int]:
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

    def _receive_can_frame(self, sock: socket.socket, mux: int) -> Dict[str, int]:
        """Recursively receive can frames until the mux is the expected value."""
        try:
            frame = sock.recv(self.FRAME_SIZE)
        except TimeoutError:
            print(f"\033[1;33mWARNING: timeout receiving can frame for mux {mux}\033[0m")
            if mux != Mux.PING:
                self.missing_responses[sock].append(time.time())
            return -1
        parsed_frame = self._parse_can_frame(frame)
        self._check_for_faults(self.CAN_ID_FAULT_CODES, parsed_frame["fault_flags"], parsed_frame["actuator_can_id"])

        if parsed_frame["mux"] != mux:
            print(f"\033[1;33mWARNING: unexpected mux 0x{parsed_frame['mux']:02X} in feedback response\033[0m")
            if parsed_frame["mux"] == Mux.FAULT_RESPONSE:
                self._process_fault_response(parsed_frame["payload"], parsed_frame["actuator_can_id"])
                return self._receive_can_frame(sock, mux)  # call again recursively
        else:
            return parsed_frame

    def _check_for_faults(self, faults: list[FaultCode], fault_flags: int, actuator_can_id: int) -> None:
        for fault_code in faults:
            if fault_flags == fault_code.code:
                if fault_code.critical:
                    raise CriticalFaultError(
                        f"\033[1;31mCRITICAL FAULT: actuator {actuator_can_id} has {fault_code.description}\033[0m"
                    )
                else:
                    print(f"\033[1;33mWARNING: actuator {actuator_can_id} has {fault_code.description}\033[0m")

    def _process_fault_response(self, payload: bytes, actuator_can_id: int) -> None:
        fault_value, warning_value = struct.unpack("<II", payload)  # Little-endian uint32
        self._check_for_faults(self.MUX_0x15_FAULT_CODES, fault_value, actuator_can_id)
        self._check_for_faults(self.MUX_0x15_WARNING_CODES, warning_value, actuator_can_id)

    def _find_actuators(self) -> None:
        print("\033[1;36m🔍 Scanning CAN buses for actuators...\033[0m")
        for canbus in self.canbus_range:
            print(f"Scanning bus {canbus}: ", end="")
            sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            try:
                sock.bind((f"can{canbus}",))
                sock.settimeout(0.005)
                sock.send(self._build_can_frame(0, Mux.PING))  # test message
                self.sockets[canbus] = sock
                self.actuators[canbus] = []
                print("\033[92mSuccess\033[0m")
            except Exception:
                print("\033[91mFailed\033[0m")
                continue

            for actuator_id in self.actuator_range:
                if self._ping_actuator(canbus, actuator_id) != -1:
                    self.actuators[canbus].append(actuator_id)
                self.actuators[canbus] = list(set(self.actuators[canbus]))

        total_actuators = sum(len(actuators) for actuators in self.actuators.values())
        print(f"\033[1;32mFound {total_actuators} actuators on {len(self.sockets)} sockets\033[0m")
        for canbus, actuators in self.actuators.items():
            print(f"\033[1;34m{canbus}\033[0m: \033[1;35m{actuators}\033[0m")

    def _ping_actuator(self, canbus: str, actuator_can_id: int) -> bool:
        frame = self._build_can_frame(actuator_can_id, Mux.PING)
        self.sockets[canbus].send(frame)
        response = self._receive_can_frame(self.sockets[canbus], Mux.PING)
        if response == -1:
            return -1
        return response["actuator_can_id"]

    def enable_motors(self) -> None:
        for canbus in self.sockets.keys():
            for actuator_id in self.actuators[canbus]:
                self._enable_motor(canbus, actuator_id)

    def _enable_motor(self, canbus: int, actuator_can_id: int) -> None:
        frame = self._build_can_frame(actuator_can_id, Mux.MOTOR_ENABLE)
        self.sockets[canbus].send(frame)
        _ = self._receive_can_frame(self.sockets[canbus], Mux.FEEDBACK)

    def get_actuator_feedback(self) -> Dict[str, int]:
        """Send one message per bus; wait for all of them concurrently."""
        results = {}
        max_tranches = max(len(self.actuators[can]) for can in self.actuators.keys())
        for tranche in range(max_tranches):
            for can, sock in self.sockets.items():
                if tranche < len(self.actuators[can]):
                    actuator_id = self.actuators[can][tranche]
                    frame = self._build_can_frame(actuator_id, Mux.FEEDBACK)
                    sock.send(frame)
            for can, sock in self.sockets.items():
                if tranche < len(self.actuators[can]):
                    actuator_id = self.actuators[can][tranche]
                    frame = self._receive_can_frame(sock, Mux.FEEDBACK)
                    if frame == -1: # timeout
                        continue
                    result = self._parse_feedback_response(frame)
                    if actuator_id != result["actuator_can_id"]:  # TODO enforce and flush
                        print(f"\033[1;33mWARNING: actuator {actuator_id} != {result['actuator_can_id']}\033[0m")
                        actuator_id = result["actuator_can_id"]
                    results[actuator_id] = result
        return results

    def _parse_feedback_response(self, result: bytes) -> Dict[str, int]:
        angle_be, ang_vel_be, torque_be, temp_be = struct.unpack(">HHHH", result["payload"])
        return {
            "host_id": result["host_id"],
            "actuator_can_id": result["actuator_can_id"],
            "fault_flags": result["fault_flags"],
            "angle_raw": angle_be,
            "angular_velocity_raw": ang_vel_be,
            "torque_raw": torque_be,
            "temperature_raw": temp_be,
        }

    def set_pd_targets(self, actions: dict[int, float], robotcfg: RobotConfig, scaling: float) -> None:
        for canbus in self.sockets.keys():
            for actuator_id in self.actuators[canbus]:
                if actuator_id in actions:  # Only send commands to actuators in the actions dict
                    frame = self._build_pd_command_frame(actuator_id, actions[actuator_id], robotcfg, scaling)
                    self.sockets[canbus].send(frame)
        for canbus in self.sockets.keys():
            for actuator_id in self.actuators[canbus]:
                if actuator_id in actions:  # Only wait for responses from actuators we commanded
                    frame = self._receive_can_frame(self.sockets[canbus], Mux.FEEDBACK)

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

    def receive_missing_responses(self) -> None:
        """Single-pass drain of late responses"""
        # Prune stale entries (>1s)
        now_s = time.time()
        self.missing_responses = {sock: [t for t in timestamps if (now_s - t) < 1.0] for sock, timestamps in self.missing_responses.items()}
        total_missing_responses = sum(len(timestamps) for timestamps in self.missing_responses.values())
        if not total_missing_responses:
            return
        print(f"Total missing responses: {total_missing_responses}")

        # Try to read from sockets with pending responses
        sockets = list(self.missing_responses.keys())
        try:
            readable, _, _ = select.select(sockets, [], [], timeout=0.001)
        except Exception:
            print(f"\033[1;33mWARNING: exception in receive_missing_responses\033[0m")
            return

        # Process any readable sockets
        for sock in readable:
            if (frame := self._receive_can_frame(sock, Mux.FEEDBACK)) != -1:
                # Remove the oldest missing response
                self.missing_responses[sock].remove(self.missing_responses[sock][0])


class MotorDriver:
    """Driver logic."""

    def __init__(self, max_scaling: float = 1.0) -> None:
        self.max_scaling = max_scaling
        self.robot = RobotConfig()
        self.ci = CANInterface()
        self.startup_sequence()

    def startup_sequence(self) -> None:
        states = self.ci.get_actuator_feedback()

        print("\033[1;36mActuator states:\033[0m")
        print("ID  | Nam | Angle | Velocity | Torque | Temp  | Faults")
        print("----|-----|-------|----------|--------|-------|-------")
        for act_id, state in states.items():
            name = self.robot.actuators[act_id].name[:3]
            fault_color = "\033[1;31m" if state["fault_flags"] > 0 else "\033[1;32m"
            angle = self.robot.actuators[act_id].can_to_physical_angle(state["angle_raw"])
            velocity = self.robot.actuators[act_id].can_to_physical_velocity(state["angular_velocity_raw"])
            torque = self.robot.actuators[act_id].can_to_physical_torque(state["torque_raw"])
            temp = self.robot.actuators[act_id].can_to_physical_temperature(state["temperature_raw"])
            print(
                f"{act_id:3d} | {name:3s} | \033[1;34m{angle:5.2f}\033[0m | "
                f"\033[1;35m{velocity:8.2f}\033[0m | \033[1;33m{torque:6.2f}\033[0m | "
                f"\033[1;36m{temp:5.1f}\033[0m | {fault_color}{state['fault_flags']:3d}\033[0m"
            )

        if not states:
            print("\033[1;31m❌ No actuators detected\033[0m")
            sys.exit(1)

        angles = {
            act_id: self.robot.actuators[act_id].can_to_physical_angle(state["angle_raw"])
            for act_id, state in states.items()
        }
        if any(abs(angle) > 2.0 for angle in angles.values()):
            print("\033[1;31m❌ Actuator angles too far from zero - move joints closer to home position\033[0m")
            sys.exit(1)

        if any(state["fault_flags"] > 0 for state in states.values()):
            print("\033[1;31m❌ Actuator faults detected\033[0m")

        print("Press Enter to enable motors...")
        input()  # wait for user to enable motors
        self.ci.enable_motors()
        print("✅ Motors enabled")
        print("\nHoming...")
        home_targets = {id: self.robot.actuators[id].joint_bias for id in self.robot.actuators.keys()}
        for scale in [math.exp(math.log(0.001) + (math.log(1.0) - math.log(0.001)) * i / 29) for i in range(30)]:
            if scale > self.max_scaling:
                break
            print(f"PD ramp: {scale:.3f}")
            self.ci.set_pd_targets(home_targets, robotcfg=self.robot, scaling=scale)
            time.sleep(0.1)
        print("✅ Homing complete")

    def sine_wave(self) -> None:
        t0 = time.perf_counter()
        while True:
            t = time.perf_counter()
            _ = self.ci.get_actuator_feedback()
            t1 = time.perf_counter()
            angle = 0.3 * math.sin(2 * math.pi * 0.5 * (t - t0))
            action = {id: angle + self.robot.actuators[id].joint_bias for id in self.robot.actuators.keys()}
            t2 = time.perf_counter()
            self.ci.set_pd_targets(action, robotcfg=self.robot, scaling=self.max_scaling)
            t3 = time.perf_counter()
            print(f"get feedback={(t1 - t) * 1e6:.0f}us, set targets={(t3 - t2) * 1e6:.0f}us")
            time.sleep(max(0.02 - (time.perf_counter() - t), 0))

    def receive_missing_responses(self) -> None:
        self.ci.receive_missing_responses()

    def get_joint_angles_and_velocities(self, joint_order: list[str]) -> tuple[list[float], list[float]]:
        fb = self.ci.get_actuator_feedback()
        joint_angles, joint_vels, torques, temps = {}, {}, {}, {}
        for id in self.robot.actuators.keys():
            if id in fb:
                joint_angles[id] = self.robot.actuators[id].can_to_physical_angle(fb[id]["angle_raw"])
                joint_vels[id] = self.robot.actuators[id].can_to_physical_velocity(fb[id]["angular_velocity_raw"])
                torques[id] = self.robot.actuators[id].can_to_physical_torque(fb[id]["torque_raw"])
                temps[id] = self.robot.actuators[id].can_to_physical_temperature(fb[id]["temperature_raw"])
            else:  # fill absent actuators with zeros
                joint_angles[id], joint_vels[id], torques[id], temps[id] = 0.0, 0.0, 0.0, 0.0

        joint_angles_ordered = [joint_angles[self.robot.full_name_to_actuator_id[name]] for name in joint_order]
        joint_vels_ordered = [joint_vels[self.robot.full_name_to_actuator_id[name]] for name in joint_order]
        torques_ordered = [torques[self.robot.full_name_to_actuator_id[name]] for name in joint_order]
        temps_ordered = [temps[self.robot.full_name_to_actuator_id[name]] for name in joint_order]
        return joint_angles_ordered, joint_vels_ordered, torques_ordered, temps_ordered

    def take_action(self, action: list[float], joint_order: list[str]) -> None:
        action = {self.robot.full_name_to_actuator_id[name]: action for name, action in zip(joint_order, action)}
        self.ci.set_pd_targets(action, robotcfg=self.robot, scaling=self.max_scaling)


def main() -> None:
    driver = MotorDriver(max_scaling=0.1)
    input("Press Enter to run sine wave on all actuators...")
    driver.sine_wave()


if __name__ == "__main__":
    main()


# # .recv takes 10-30us if messages are available.

# # TODO dont die on critical faults?
# TODO if missing response - feed last known good value instead of 0
