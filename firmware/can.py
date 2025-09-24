from dataclasses import dataclass
import math
import socket
import struct
import time
from typing import Dict

from robot import RobotConfig

class CriticalFault(Exception): pass


@dataclass
class FaultCode:
    code: int
    critical: bool
    description: str


class CANInterface:
    """Communication only."""

    def __init__(self):
        self.FRAME_FMT = "<IBBBB8s"  # <I = little-endian u32; 4B = len, pad, res0, len8_dlc; 8s = 8 data bytes
        self.FRAME_SIZE = struct.calcsize(self.FRAME_FMT)
        self.EFF = 0x8000_0000
        self.host_id = 0xFD
        self.canbus_range = range(0, 7)
        self.actuator_range = range(10, 50)

        # mux codes
        self.MUX_PING = 0x00
        self.MUX_CONTROL = 0x01
        self.MUX_FEEDBACK = 0x02
        self.MUX_MOTOR_ENABLE = 0x03
        self.MUX_FAULT_RESPONSE = 0x15

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
            FaultCode(0x200000, False, "Uncalibrated"),
            FaultCode(0x100000, False, "Gridlock overload fault"),
            FaultCode(0x080000, False, "Magnetic coding fault"),
            FaultCode(0x040000, True, "Overtemperature"),
            FaultCode(0x020000, True, "Overcurrent"),
            FaultCode(0x010000, False, "Undervoltage"),
        ]

        self.sockets = {}
        self.actuators = {}
        self._find_actuators()

    def _build_can_frame(self, actuator_can_id: int, mux: int, payload: bytes = b"\x00" * 8) -> bytes:
        can_id = ((actuator_can_id & 0xFF) | ((self.host_id) << 8) | ((mux & 0x1F) << 24)) | self.EFF
        return struct.pack(self.FRAME_FMT, can_id, 8 & 0xFF, 0, 0, 0, payload[:8])

    def _parse_can_frame(self, frame: bytes) -> Dict[str, int]:
        if len(frame) != 16:
            raise ValueError("frame must be exactly 16 bytes")
        can_id, _length, _pad, _res0, _len8, payload = struct.unpack(self.FRAME_FMT, frame)
        b0 = (can_id >> 0) & 0xFF  # host_id (u8)
        b1 = (can_id >> 8) & 0xFF  # actuator_can_id (u8)
        b2 = (can_id >> 16) & 0xFF  # fault_flags (u8)
        b3 = (can_id >> 24) & 0xFF  # mux + EFF-in-byte
        mux = b3 & 0x1F
        return {
            "host_id": b0,
            "actuator_can_id": b1,
            "fault_flags": b2,
            "mux": mux,
            "payload": payload,
        }

    def _receive_can_frame(self, sock: socket.socket, mux: int) -> Dict[str, int]:
        """ Recursively receive can frames until the mux is the expected value. """
        frame = sock.recv(self.FRAME_SIZE)
        parsed_frame = self._parse_can_frame(frame)
        self._check_for_faults(self.CAN_ID_FAULT_CODES, parsed_frame['fault_flags'], parsed_frame['actuator_can_id'])
    
        if parsed_frame["mux"] != mux:
            print(f"\033[1;33mWARNING: unexpected mux 0x{parsed_frame['mux']:02X} in feedback response\033[0m")
            if parsed_frame["mux"] == self.MUX_FAULT_RESPONSE:
                self._process_fault_response(parsed_frame['payload'], parsed_frame['actuator_can_id'])
                return self._receive_can_frame(sock, mux) # call again recursively
        else:
            return parsed_frame

    def _check_for_faults(self, faults: list[FaultCode], fault_flags: int, actuator_can_id: int) -> None:
        for fault_code in faults:
            if fault_flags == fault_code.code:
                if fault_code.critical:
                    raise CriticalFault(f"\033[1;31mCRITICAL FAULT: actuator {actuator_can_id} has {fault_code.description}\033[0m")
                else:
                    print(f"\033[1;33mWARNING: actuator {actuator_can_id} has {fault_code.description}\033[0m")

    def _process_fault_response(self, payload: bytes, actuator_can_id: int) -> None:
        fault_value, warning_value = struct.unpack("<II", payload)  # Little-endian uint32
        self._check_for_faults(self.MUX_0x15_FAULT_CODES, fault_value, actuator_can_id)
        self._check_for_faults(self.MUX_0x15_WARNING_CODES, warning_value, actuator_can_id)

    def _receive_all_can_frames(self, canbus: int) -> list[bytes]:
        frames = []
        t0 = time.perf_counter()
        while True:
            try:
                frame = self.sockets[canbus].recv(self.FRAME_SIZE)
                frames.append(frame)
            except:
                break
        if len(frames) > 0:
            print(f"received {len(frames)} frames in {(time.perf_counter() - t0) * 1e6:.2f}us")
        return frames

    def _find_actuators(self) -> None:
        print("\033[1;36m🔍 Scanning CAN buses for actuators...\033[0m")
        for canbus in self.canbus_range:
            print(f"Scanning bus {canbus}: ", end="")
            sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            try:
                sock.bind((f"can{canbus}",))
                sock.settimeout(0.002)
                sock.send(self._build_can_frame(0, self.MUX_PING))  # test message
                self.sockets[canbus] = sock
                self.actuators[canbus] = []
                print("\033[92mSuccess\033[0m")
            except Exception:
                print("\033[91mFailed\033[0m")
                continue

            for actuator_id in self.actuator_range: # TODO move inside try above, instaed of test message. 
                if self._ping_actuator(canbus, actuator_id):
                    self.actuators[canbus].append(actuator_id)

        total_actuators = sum(len(actuators) for actuators in self.actuators.values())
        print(f"\033[1;32mFound {total_actuators} actuators on {len(self.sockets)} sockets\033[0m")
        for canbus, actuators in self.actuators.items():
            print(f"\033[1;34m{canbus}\033[0m: \033[1;35m{actuators}\033[0m")

    def _ping_actuator(self, canbus: str, actuator_can_id: int) -> bool:
        frame = self._build_can_frame(actuator_can_id, self.MUX_PING)
        self.sockets[canbus].send(frame)
        frames = self._receive_all_can_frames(canbus)
        for i, frame in enumerate(frames):
            result = self._parse_can_frame(frame)
            print(f"\tFrame {i}: {result['actuator_can_id']}::{result['mux']}")
        return len(frames) > 0

    def enable_motors(self):
        for canbus in self.sockets.keys():
            for actuator_id in self.actuators[canbus]:
                self._enable_motor(canbus, actuator_id)

    def _enable_motor(self, canbus: int, actuator_can_id: int):
        frame = self._build_can_frame(actuator_can_id, self.MUX_MOTOR_ENABLE)
        self.sockets[canbus].send(frame)
        _ = self.sockets[canbus].recv(self.FRAME_SIZE)  # receive response to keep can buffer clear

    def get_actuator_feedback(self) -> Dict[str, int]:
        """Send 1 message on each bus, and wait for all of them at once. - 3ms vs 10ms for sequential"""
        results = {}
        max_tranches = max(len(self.actuators[can]) for can in self.actuators.keys())
        for tranche in range(max_tranches):
            for can, sock in self.sockets.items():
                if tranche < len(self.actuators[can]):
                    actuator_id = self.actuators[can][tranche]
                    frame = self._build_can_frame(actuator_id, self.MUX_FEEDBACK)
                    sock.send(frame)
            for can, sock in self.sockets.items():
                if tranche < len(self.actuators[can]):
                    actuator_id = self.actuators[can][tranche]
                    parsed_frame = self._receive_can_frame(sock, self.MUX_FEEDBACK)
                    result = self._parse_feedback_response(parsed_frame)
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

    def set_pd_targets(self, actions: dict[int, float], robotcfg: RobotConfig, scaling: float):
        for canbus in self.sockets.keys():
            for actuator_id in self.actuators[canbus]:
                frame = self._build_pd_command_frame(actuator_id, actions[actuator_id], robotcfg, scaling)
                self.sockets[canbus].send(frame)
        for canbus in self.sockets.keys():
            for actuator_id in self.actuators[canbus]:
                try:
                    _ = self.sockets[canbus].recv(self.FRAME_SIZE) # drop responses
                except:
                    print("lost response on pd target send") # NOTE might cause async issues

    def _build_pd_command_frame(self, actuator_can_id: int, angle: float, robotcfg: RobotConfig, scaling: float):
        assert 0.0 <= scaling <= 1.0
        raw_torque = int(robotcfg.actuators[actuator_can_id].physical_to_can_torque(0))
        raw_angle = int(robotcfg.actuators[actuator_can_id].physical_to_can_angle(angle))
        raw_ang_vel = int(robotcfg.actuators[actuator_can_id].physical_to_can_velocity(0))
        raw_kp = int(robotcfg.actuators[actuator_can_id].raw_kp * scaling)
        raw_kd = int(robotcfg.actuators[actuator_can_id].raw_kd * scaling)

        can_id = ((actuator_can_id & 0xFF) | (raw_torque << 8) | ((self.MUX_CONTROL & 0x1F) << 24)) | self.EFF
        payload = struct.pack(">HHHH", raw_angle, raw_ang_vel, raw_kp, raw_kd)
        return struct.pack(self.FRAME_FMT, can_id, 8 & 0xFF, 0, 0, 0, payload[:8])


class MotorDriver:
    """Driver logic."""

    def __init__(self, max_scaling: float = 1.0):
        self.max_scaling = max_scaling
        self.robot = RobotConfig()
        self.ci = CANInterface()
        self.startup_sequence()

    def startup_sequence(self):
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
                f"{act_id:3d} | {name:3s} | \033[1;34m{angle:5.2f}\033[0m | \033[1;35m{velocity:8.2f}\033[0m | \033[1;33m{torque:6.2f}\033[0m | \033[1;36m{temp:5.1f}\033[0m | {fault_color}{state['fault_flags']:3d}\033[0m"
            )

        if any(state["fault_flags"] > 0 for state in states.values()):
            print("\033[1;31m❌ Actuator faults detected\033[0m")
            # exit(1) # TODO for some reason we get 128 uncalibrated faults

        input("Press Enter to enable motors...")
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

    def sine_wave(self):
        t0 = time.perf_counter()
        while True:
            angle = 3.14158 / 10 * math.sin(2 * math.pi * 0.5 * (time.perf_counter() - t0))
            action = {id: angle + self.robot.actuators[id].joint_bias for id in self.robot.actuators.keys()}
            self.ci.set_pd_targets(action, robotcfg=self.robot, scaling=self.max_scaling)
            time.sleep(0.1)

    def get_joint_angles_and_velocities(self, joint_order: list[str]) -> tuple[list[float], list[float]]:
        fb = self.ci.get_actuator_feedback()
        joint_angles, joint_velocities = {}, {}
        for id in self.robot.actuators.keys():
            if id in fb:
                joint_angles[id] = self.robot.actuators[id].can_to_physical_angle(fb[id]["angle_raw"])
                joint_velocities[id] = self.robot.actuators[id].can_to_physical_velocity(fb[id]["angular_velocity_raw"])
            else:  # fill absent actuators with zeros
                joint_angles[id], joint_velocities[id] = 0.0, 0.0

        joint_angles_ordered = [joint_angles[self.robot.full_name_to_actuator_id[name]] for name in joint_order]
        joint_velocities_ordered = [joint_velocities[self.robot.full_name_to_actuator_id[name]] for name in joint_order]
        return joint_angles_ordered, joint_velocities_ordered

    def take_action(self, action: list[float], joint_order: list[str]):
        action = {self.robot.full_name_to_actuator_id[name]: action for name, action in zip(joint_order, action)}
        self.ci.set_pd_targets(action, robotcfg=self.robot, scaling=self.max_scaling)


def main():
    driver = MotorDriver(max_scaling=0.1)
    input("Press Enter to run sine wave on all actuators...")
    driver.sine_wave()


if __name__ == "__main__":
    exit(0 if main() else 1)


# .recv takes 10-30us if messages are available.
