"""CAN communication and motor driver interfaces for actuators."""

import math
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

    # Constants
    FRAME_FMT = "<IBBBB8s"
    FRAME_SIZE = struct.calcsize(FRAME_FMT)
    EFF = 0x8000_0000
    HOST_ID = 0xFD
    CAN_TIMEOUT = 0.002
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

    def __init__(self) -> None:
        self.sockets = {}
        self.actuators = {}
        self._find_actuators()

    def _build_can_frame(self, actuator_can_id: int, mux: int, payload: bytes = b"\x00" * 8) -> bytes:
        can_id = ((actuator_can_id & 0xFF) | (self.HOST_ID << 8) | ((mux & 0x1F) << 24)) | self.EFF
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
            parsed_frame = self._parse_can_frame(frame)
        except Exception:
            return -1

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
                msg = f"Actuator {actuator_can_id}: {fault_code.description}"
                if fault_code.critical:
                    raise CriticalFaultError(f"\033[1;31mCRITICAL FAULT: {msg}\033[0m")
                print(f"\033[1;33mWARNING: {msg}\033[0m")

    def _process_fault_response(self, payload: bytes, actuator_can_id: int) -> None:
        fault_value, warning_value = struct.unpack("<II", payload)  # Little-endian uint32
        self._check_for_faults(self.MUX_0x15_FAULT_CODES, fault_value, actuator_can_id)
        self._check_for_faults(self.MUX_0x15_WARNING_CODES, warning_value, actuator_can_id)

    def _find_actuators(self) -> None:
        print("\033[1;36m🔍 Scanning CAN buses for actuators...\033[0m")
        for canbus in self.CANBUS_RANGE:
            sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            try:
                sock.bind((f"can{canbus}",))
                sock.settimeout(self.CAN_TIMEOUT)
                sock.send(self._build_can_frame(0, Mux.PING))  # test message
            except Exception:
                continue

            print(f"Scanning bus {canbus}...")
            actuators = []
            for actuator_id in self.ACTUATOR_RANGE:
                if self._ping_actuator(sock, actuator_id) != -1:
                    actuators.append(actuator_id)
            if actuators:
                self.sockets[canbus] = sock
                self.actuators[canbus] = sorted(list(set(actuators)))

        total_actuators = sum(len(actuators) for actuators in self.actuators.values())
        print(f"\033[1;32mFound {total_actuators} actuators on {len(self.sockets)} sockets\033[0m")
        for canbus, actuators in self.actuators.items():
            print(f"\033[1;34m{canbus}\033[0m: \033[1;35m{actuators}\033[0m")

    def _ping_actuator(self, sock: socket.socket, actuator_can_id: int) -> bool:
        frame = self._build_can_frame(actuator_can_id, Mux.PING)
        sock.send(frame)
        response = self._receive_can_frame(sock, Mux.PING)
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
            # Send requests
            for can, sock in self.sockets.items():
                if tranche < len(self.actuators[can]):
                    actuator_id = self.actuators[can][tranche]
                    frame = self._build_can_frame(actuator_id, Mux.FEEDBACK)
                    sock.send(frame)

            # Receive responses
            for can, sock in self.sockets.items():
                if tranche < len(self.actuators[can]):
                    actuator_id = self.actuators[can][tranche]
                    frame = self._receive_can_frame(sock, Mux.FEEDBACK)
                    if frame == -1:  # timeout
                        print(f"\033[1;33mWARNING: [gaf] recv timeout actuator {actuator_id}\033[0m")
                        continue
                    result = self._parse_feedback_response(frame)
                    if actuator_id != result["actuator_can_id"]:  # TODO enforce and flush
                        print(
                            f"\033[1;33mWARNING: [gaf] expected {actuator_id}, got {result['actuator_can_id']}\033[0m"
                        )
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
        # Send all commands
        for bus in self.sockets.keys():
            for actuator_id in self.actuators[bus]:
                if actuator_id in actions:
                    frame = self._build_pd_command_frame(actuator_id, actions[actuator_id], robotcfg, scaling)
                    self.sockets[bus].send(frame)

        # Receive all responses
        for bus in self.sockets.keys():
            for actuator_id in self.actuators[bus]:
                if actuator_id in actions:  # Only wait for responses from actuators we commanded
                    frame = self._receive_can_frame(self.sockets[bus], Mux.FEEDBACK)
                    if frame == -1:  # timeout
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

    def flush_can_busses(self) -> None:
        """Try to drain 1 message from each CAN bus.

        Actuators sometimes send late or extra messages that we need to get rid of.
        """
        for canbus, sock in self.sockets.items():
            result = self._receive_can_frame(sock, Mux.FEEDBACK)
            if result != -1:
                print(f"\033[1;32mflushed message on bus {canbus}\033[0m")


class MotorDriver:
    """Driver logic."""

    def __init__(self, max_scaling: float = 1.0) -> None:
        self.max_scaling = max_scaling
        self.robot = RobotConfig()
        self.can = CANInterface()
        # Cache for last known good values (initialized to zeros)
        self.last_known_feedback = {
            id: robot.dummy_data() for id, robot in self.robot.actuators.items()
        }
        self.startup_sequence()

    def ramp_down_motors(self) -> None:
        """Gradually ramp down motor torques before disabling (inverse of enable_and_home)."""
        print("Ramping down motors...")
        try:
            # Get CURRENT positions as targets (not home positions!)
            # This prevents the robot from violently snapping to home position
            joint_data: dict[int, dict[str, float]] = self.get_joint_angles_and_velocities()
            joint_angles: dict[int, float] = {id: data["angle"] for id, data in joint_data.items()}
            # Safety check: only proceed if we have at least one actuator responding
            if len(joint_data) == 0:
                print("No actuators responding, skipping ramp down")
                return
            
            print(f"Ramping down {len(joint_data)} actuators")
            # Ramp down from current scaling to 0 (reverse of ramp up)
            for scale in reversed([math.exp(math.log(0.001) + (math.log(1.0) - math.log(0.001)) * i / 49) for i in range(50)]):
                self.can.set_pd_targets(joint_angles, robotcfg=self.robot, scaling=scale)
                time.sleep(0.05)  # Slower ramp down for safety
            
            # Final zero torque command
            self.can.set_pd_targets(joint_angles, robotcfg=self.robot, scaling=0.0)
            print("✅ Motors ramped down")
        except Exception as e:
            print(f"Error during motor ramp down: {e}")

    def startup_sequence(self) -> None:
        if not self.can.actuators:
            print("\033[1;31mERROR: No actuators detected\033[0m")
            sys.exit(1)

        joint_data_dict= self.get_joint_angles_and_velocities()

        print("\nActuator states:")
        print("ID  | Name | Angle | Velocity | Torque | Temp  | Faults")
        print("----|------|-------|----------|--------|-------|-------")
        for act_id, data in joint_data_dict.items():
            fault_color = "\033[1;31m" if data["fault_flags"] > 0 else "\033[1;32m"
            print(
                f"{act_id:3d} | {data['name']:14s} | {data['angle']:5.2f} | {data['velocity']:8.2f} | "
                f"{data['torque']:6.2f} | {data['temperature']:5.1f} | {fault_color}{data['fault_flags']:3d}\033[0m"
            )
            if data["fault_flags"] > 0:
                print("\033[1;33mWARNING: Actuator faults detected\033[0m")
        if any(abs(data["angle"]) > 2.0 for data in joint_data_dict.values()):
            print("\033[1;31mERROR: Actuator angles too far from zero - move joints closer to home position\033[0m")
            sys.exit(1)
        print("Press Enter to enable motors...")
        input()  # wait for user to enable motors
        self.can.enable_motors()
        print("✅ Motors enabled")

        print("\nHoming...")
        home_targets = {id: self.robot.actuators[id].joint_bias for id in self.robot.actuators.keys()}
        for i in range(30):
            scale = math.exp(math.log(0.001) + (math.log(1.0) - math.log(0.001)) * i / 29)
            if scale > self.max_scaling:
                break
            print(f"PD ramp: {scale:.3f}")
            self.can.set_pd_targets(home_targets, robotcfg=self.robot, scaling=scale)
            time.sleep(0.1)
        print("✅ Homing complete")

    def sine_wave(self) -> None:
        """Run a sine wave motion on all actuators."""
        t0 = time.perf_counter()
        while True:
            t = time.perf_counter()
            _ = self.can.get_actuator_feedback()
            t1 = time.perf_counter()
            angle = 0.3 * math.sin(2 * math.pi * 0.5 * (t - t0))
            action = {id: angle + self.robot.actuators[id].joint_bias for id in self.robot.actuators.keys()}
            t2 = time.perf_counter()
            self.can.set_pd_targets(action, robotcfg=self.robot, scaling=self.max_scaling)
            t3 = time.perf_counter()
            self.can.flush_can_busses()
            t4 = time.perf_counter()
            print(
                f"get feedback={(t1 - t) * 1e6:.0f}us, "
                f"set targets={(t3 - t2) * 1e6:.0f}us, "
                f"receive missing responses={(t4 - t3) * 1e6:.0f}us"
            )
            time.sleep(max(0.02 - (time.perf_counter() - t), 0))

    def flush_can_busses(self) -> None:
        self.can.flush_can_busses()

    def get_joint_angles_and_velocities(self) -> dict[int, dict[str, float]]:
        fb = self.can.get_actuator_feedback()
        answer = {}
        for id in self.robot.actuators.keys():
            if id in fb:
                answer[id] = self.robot.actuators[id].can_to_physical_data(fb[id])
                self.last_known_feedback[id] = answer[id].copy()
                
            elif id in self.last_known_feedback:
                # Fall back to last known good values
                answer[id] = self.last_known_feedback[id].copy()
            else:
                # Ultimate fallback to zeros for unknown actuators
                answer[id] = self.robot.actuators[id].dummy_data()
        return answer

    def get_ordered_joint_data(self, joint_order: list[str]) -> tuple[list[float], list[float], list[float], list[float]]:
        joint_data_dict= self.get_joint_angles_and_velocities()

        joint_angles_order, joint_vels_order, torques_order, temps_order = [], [], [], []

        for name in joint_order:
            id = self.robot.full_name_to_actuator_id[name]
            joint_data = joint_data_dict[id]
            joint_angles_order.append(joint_data["angle"])
            joint_vels_order.append(joint_data["velocity"])
            torques_order.append(joint_data["torque"])
            temps_order.append(joint_data["temperature"])

        return joint_angles_order, joint_vels_order, torques_order, temps_order

    def take_action(self, action: list[float], joint_order: list[str]) -> None:
        action = {self.robot.full_name_to_actuator_id[name]: action for name, action in zip(joint_order, action)}
        self.can.set_pd_targets(action, robotcfg=self.robot, scaling=self.max_scaling)


def main() -> None:
    driver = MotorDriver(max_scaling=0.1)
    input("Press Enter to run sine wave on all actuators...")
    driver.sine_wave()


if __name__ == "__main__":
    main()


# # .recv takes 10-30us if messages are available.
# TODO reset motor after critical fault?
# TODO reset all act upons startup
# # TODO dont die on critical faults?
# upd listener .clip ccmds
