"""Actuator configuration, conversion utilities, and robot configuration data."""

import math
from dataclasses import dataclass
from enum import Enum
from math import pi


@dataclass
class Mux:
    PING: int = 0x00
    CONTROL: int = 0x01
    FEEDBACK: int = 0x02
    MOTOR_ENABLE: int = 0x03
    FAULT_RESPONSE: int = 0x15


@dataclass
class FaultCode:
    code: int
    critical: bool
    description: str


class RobstrideActuatorType(Enum):
    Robstride00 = 0
    Robstride01 = 1
    Robstride02 = 2
    Robstride03 = 3
    Robstride04 = 4


@dataclass
class ActuatorConfig:
    can_id: int
    full_name: str
    actuator_type: RobstrideActuatorType
    joint_bias: float
    kp: float
    kd: float
    # can ranges:
    angle_can_min: float
    angle_can_max: float
    velocity_can_min: float
    velocity_can_max: float
    torque_can_min: float
    torque_can_max: float
    kp_can_min: float
    kp_can_max: float
    kd_can_min: float
    kd_can_max: float

    def dummy_data(self) -> dict[str, float | str]:
        return {"name": self.name, "fault_flags": 0, "angle": 0.0, "velocity": 0.0, "torque": 0.0, "temperature": 0.0}

    def can_to_physical_data(self, fb: dict[str, int]) -> dict[str, float | str | int]:
        actuator_data: dict[str, float | str | int] = {
            "name": self.name,
            "full_name": self.full_name,
            "fault_flags": fb["fault_flags"],
            "angle": self.can_to_physical_angle(fb["angle_raw"]),
            "velocity": self.can_to_physical_velocity(fb["angular_velocity_raw"]),
            "torque": self.can_to_physical_torque(fb["torque_raw"]),
            "temperature": self.can_to_physical_temperature(fb["temperature_raw"]),
        }
        return actuator_data

    def can_to_physical_angle(self, can_value: float) -> float:
        proportion = (can_value - 0.0) / (65535.0 - 0.0)
        return self.angle_can_min + proportion * (self.angle_can_max - self.angle_can_min)

    def physical_to_can_angle(self, physical_value: float) -> float:
        proportion = (physical_value - self.angle_can_min) / (self.angle_can_max - self.angle_can_min)
        return 0.0 + proportion * (65535.0 - 0.0)

    def can_to_physical_velocity(self, can_value: float) -> float:
        proportion = (can_value - 0.0) / (65535.0 - 0.0)
        return self.velocity_can_min + proportion * (self.velocity_can_max - self.velocity_can_min)

    def physical_to_can_velocity(self, physical_value: float) -> float:
        proportion = (physical_value - self.velocity_can_min) / (self.velocity_can_max - self.velocity_can_min)
        return 0.0 + proportion * (65535.0 - 0.0)

    def can_to_physical_torque(self, can_value: float) -> float:
        proportion = (can_value - 0.0) / (65535.0 - 0.0)
        return self.torque_can_min + proportion * (self.torque_can_max - self.torque_can_min)

    def physical_to_can_torque(self, physical_value: float) -> float:
        proportion = (physical_value - self.torque_can_min) / (self.torque_can_max - self.torque_can_min)
        return 0.0 + proportion * (65535.0 - 0.0)

    def can_to_physical_kp(self, can_value: float) -> float:
        proportion = (can_value - 0.0) / (65535.0 - 0.0)
        return self.kp_can_min + proportion * (self.kp_can_max - self.kp_can_min)

    def physical_to_can_kp(self, physical_value: float) -> float:
        proportion = (physical_value - self.kp_can_min) / (self.kp_can_max - self.kp_can_min)
        return 0.0 + proportion * (65535.0 - 0.0)

    def can_to_physical_kd(self, can_value: float) -> float:
        proportion = (can_value - 0.0) / (65535.0 - 0.0)
        return self.kd_can_min + proportion * (self.kd_can_max - self.kd_can_min)

    def physical_to_can_kd(self, physical_value: float) -> float:
        proportion = (physical_value - self.kd_can_min) / (self.kd_can_max - self.kd_can_min)
        return 0.0 + proportion * (65535.0 - 0.0)

    def can_to_physical_temperature(self, can_value: float) -> float:
        return can_value / 10.0

    @property
    def raw_kp(self) -> float:
        return self.physical_to_can_kp(self.kp)

    @property
    def raw_kd(self) -> float:
        return self.physical_to_can_kd(self.kd)

    @property
    def name(self) -> str:
        parts = self.full_name.replace("dof_", "").split("_")
        return "_".join(parts[:-1])


def actuator_ranges(actuator_type: RobstrideActuatorType) -> dict[str, float]:
    if actuator_type == RobstrideActuatorType.Robstride00:
        return {
            "angle_can_min": -4.0 * pi,
            "angle_can_max": 4.0 * pi,
            "velocity_can_min": -33.0,
            "velocity_can_max": 33.0,
            "torque_can_min": -14.0,
            "torque_can_max": 14.0,
            "kp_can_min": 0.0,
            "kp_can_max": 500.0,
            "kd_can_min": 0.0,
            "kd_can_max": 5.0,
        }
    elif actuator_type == RobstrideActuatorType.Robstride01:
        return {
            "angle_can_min": -4.0 * pi,
            "angle_can_max": 4.0 * pi,
            "velocity_can_min": -44.0,
            "velocity_can_max": 44.0,
            "torque_can_min": -17.0,
            "torque_can_max": 17.0,
            "kp_can_min": 0.0,
            "kp_can_max": 500.0,
            "kd_can_min": 0.0,
            "kd_can_max": 5.0,
        }
    elif actuator_type == RobstrideActuatorType.Robstride02:
        return {
            "angle_can_min": -4.0 * pi,
            "angle_can_max": 4.0 * pi,
            "velocity_can_min": -44.0,
            "velocity_can_max": 44.0,
            "torque_can_min": -17.0,
            "torque_can_max": 17.0,
            "kp_can_min": 0.0,
            "kp_can_max": 500.0,
            "kd_can_min": 0.0,
            "kd_can_max": 5.0,
        }
    elif actuator_type == RobstrideActuatorType.Robstride03:
        return {
            "angle_can_min": -4.0 * pi,
            "angle_can_max": 4.0 * pi,
            "velocity_can_min": -20.0,
            "velocity_can_max": 20.0,
            "torque_can_min": -60.0,
            "torque_can_max": 60.0,
            "kp_can_min": 0.0,
            "kp_can_max": 5000.0,
            "kd_can_min": 0.0,
            "kd_can_max": 100.0,
        }
    elif actuator_type == RobstrideActuatorType.Robstride04:
        return {
            "angle_can_min": -4.0 * pi,
            "angle_can_max": 4.0 * pi,
            "velocity_can_min": -15.0,
            "velocity_can_max": 15.0,
            "torque_can_min": -120.0,
            "torque_can_max": 120.0,
            "kp_can_min": 0.0,
            "kp_can_max": 5000.0,
            "kd_can_min": 0.0,
            "kd_can_max": 100.0,
        }


class RobotConfig:
    actuators: dict[int, ActuatorConfig] = {
        # Left arm
        11: ActuatorConfig(
            can_id=11,
            full_name="dof_left_shoulder_pitch_03",
            actuator_type=RobstrideActuatorType.Robstride03,
            **actuator_ranges(RobstrideActuatorType.Robstride03),
            kp=100.0,
            kd=8.284,
            joint_bias=0.0,
        ),
        12: ActuatorConfig(
            can_id=12,
            full_name="dof_left_shoulder_roll_03",
            actuator_type=RobstrideActuatorType.Robstride03,
            **actuator_ranges(RobstrideActuatorType.Robstride03),
            kp=100.0,
            kd=8.257,
            joint_bias=math.radians(10.0),
        ),
        13: ActuatorConfig(
            can_id=13,
            full_name="dof_left_shoulder_yaw_02",
            actuator_type=RobstrideActuatorType.Robstride02,
            **actuator_ranges(RobstrideActuatorType.Robstride02),
            kp=100.0,
            kd=2.945,
            joint_bias=0.0,
        ),
        14: ActuatorConfig(
            can_id=14,
            full_name="dof_left_elbow_02",
            actuator_type=RobstrideActuatorType.Robstride02,
            **actuator_ranges(RobstrideActuatorType.Robstride02),
            kp=80.0,
            kd=2.266,
            joint_bias=math.radians(-90.0),
        ),
        15: ActuatorConfig(
            can_id=15,
            full_name="dof_left_wrist_00",
            actuator_type=RobstrideActuatorType.Robstride00,
            **actuator_ranges(RobstrideActuatorType.Robstride00),
            kp=20.0,
            kd=0.295,
            joint_bias=0.0,
        ),
        16: ActuatorConfig(
            can_id=16,
            full_name="dof_left_wrist_gripper_05",
            actuator_type=RobstrideActuatorType.Robstride00,
            **actuator_ranges(RobstrideActuatorType.Robstride00),
            kp=4,
            kd=0.06,
            joint_bias=math.radians(0),
        ),
        # Right arm
        21: ActuatorConfig(
            can_id=21,
            full_name="dof_right_shoulder_pitch_03",
            actuator_type=RobstrideActuatorType.Robstride03,
            **actuator_ranges(RobstrideActuatorType.Robstride03),
            kp=100.0,
            kd=8.284,
            joint_bias=0.0,
        ),
        22: ActuatorConfig(
            can_id=22,
            full_name="dof_right_shoulder_roll_03",
            actuator_type=RobstrideActuatorType.Robstride03,
            **actuator_ranges(RobstrideActuatorType.Robstride03),
            kp=100.0,
            kd=8.257,
            joint_bias=math.radians(-10.0),
        ),
        23: ActuatorConfig(
            can_id=23,
            full_name="dof_right_shoulder_yaw_02",
            actuator_type=RobstrideActuatorType.Robstride02,
            **actuator_ranges(RobstrideActuatorType.Robstride02),
            kp=100.0,
            kd=2.945,
            joint_bias=0.0,
        ),
        24: ActuatorConfig(
            can_id=24,
            full_name="dof_right_elbow_02",
            actuator_type=RobstrideActuatorType.Robstride02,
            **actuator_ranges(RobstrideActuatorType.Robstride02),
            kp=100.0,
            kd=2.266,
            joint_bias=math.radians(90.0),
        ),
        25: ActuatorConfig(
            can_id=25,
            full_name="dof_right_wrist_00",
            actuator_type=RobstrideActuatorType.Robstride00,
            **actuator_ranges(RobstrideActuatorType.Robstride00),
            kp=20.0,
            kd=0.295,
            joint_bias=0.0,
        ),
        26: ActuatorConfig(
            can_id=26,
            full_name="dof_right_wrist_gripper_05",
            actuator_type=RobstrideActuatorType.Robstride00,
            **actuator_ranges(RobstrideActuatorType.Robstride00),
            kp=4,
            kd=0.06,
            joint_bias=math.radians(0),
        ),
        # Left leg
        31: ActuatorConfig(
            can_id=31,
            full_name="dof_left_hip_pitch_04",
            actuator_type=RobstrideActuatorType.Robstride04,
            **actuator_ranges(RobstrideActuatorType.Robstride04),
            kp=150.0,
            kd=24.722,
            joint_bias=math.radians(20.0),
        ),
        32: ActuatorConfig(
            can_id=32,
            full_name="dof_left_hip_roll_03",
            actuator_type=RobstrideActuatorType.Robstride03,
            **actuator_ranges(RobstrideActuatorType.Robstride03),
            kp=200.0,
            kd=26.387,
            joint_bias=0.0,
        ),
        33: ActuatorConfig(
            can_id=33,
            full_name="dof_left_hip_yaw_03",
            actuator_type=RobstrideActuatorType.Robstride03,
            **actuator_ranges(RobstrideActuatorType.Robstride03),
            kp=100.0,
            kd=3.419,
            joint_bias=0.0,
        ),
        34: ActuatorConfig(
            can_id=34,
            full_name="dof_left_knee_04",
            actuator_type=RobstrideActuatorType.Robstride04,
            **actuator_ranges(RobstrideActuatorType.Robstride04),
            kp=150.0,
            kd=8.654,
            joint_bias=math.radians(50.0),
        ),
        35: ActuatorConfig(
            can_id=35,
            full_name="dof_left_ankle_02",
            actuator_type=RobstrideActuatorType.Robstride02,
            **actuator_ranges(RobstrideActuatorType.Robstride02),
            kp=40.0,
            kd=0.99,
            joint_bias=math.radians(-30.0),
        ),
        # Right leg
        41: ActuatorConfig(
            can_id=41,
            full_name="dof_right_hip_pitch_04",
            actuator_type=RobstrideActuatorType.Robstride04,
            **actuator_ranges(RobstrideActuatorType.Robstride04),
            kp=150.0,
            kd=24.722,
            joint_bias=math.radians(-20.0),
        ),
        42: ActuatorConfig(
            can_id=42,
            full_name="dof_right_hip_roll_03",
            actuator_type=RobstrideActuatorType.Robstride03,
            **actuator_ranges(RobstrideActuatorType.Robstride03),
            kp=200.0,
            kd=26.387,
            joint_bias=0.0,
        ),
        43: ActuatorConfig(
            can_id=43,
            full_name="dof_right_hip_yaw_03",
            actuator_type=RobstrideActuatorType.Robstride03,
            **actuator_ranges(RobstrideActuatorType.Robstride03),
            kp=100.0,
            kd=3.419,
            joint_bias=0.0,
        ),
        44: ActuatorConfig(
            can_id=44,
            full_name="dof_right_knee_04",
            actuator_type=RobstrideActuatorType.Robstride04,
            **actuator_ranges(RobstrideActuatorType.Robstride04),
            kp=150.0,
            kd=8.654,
            joint_bias=math.radians(-50.0),
        ),
        45: ActuatorConfig(
            can_id=45,
            full_name="dof_right_ankle_02",
            actuator_type=RobstrideActuatorType.Robstride02,
            **actuator_ranges(RobstrideActuatorType.Robstride02),
            kp=40.0,
            kd=0.99,
            joint_bias=math.radians(30.0),
        ),
    }

    def __init__(self) -> None:
        self.full_name_to_actuator_id = {act.full_name: act.can_id for act in self.actuators.values()}
