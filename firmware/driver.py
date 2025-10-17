"""CAN communication and motor driver interfaces for actuators."""

import math
import sys
import time

from firmware.can import CANInterface
from firmware.actuators import RobotConfig
from firmware.shutdown import get_shutdown_manager

CANBUS_RANGE = range(0, 7)

class CriticalFaultError(Exception):
    pass

class MotorDriver:
    """Driver logic."""

    def __init__(self, max_scaling: float = 1.0) -> None:
        self.max_scaling = max_scaling
        self.robot = RobotConfig()
        self.cans: list[CANInterface] = []
        for canbus in CANBUS_RANGE:
            canInterface = CANInterface()
            found_actuators = canInterface.find_actuators(canbus)
            if len(found_actuators) > 0:
                self.cans.append(canInterface)
            else: del canInterface

        self.last_known_feedback = {id: robot.dummy_data() for id, robot in self.robot.actuators.items()}
        self._motors_enabled = False
        self._last_scaling = 0.0

        shutdown_mgr = get_shutdown_manager()
        shutdown_mgr.register_cleanup("CAN sockets", self.close)  # Register first, closes last
        shutdown_mgr.register_cleanup("Motor ramp down", self._safe_ramp_down)  # Register last, executes first

        self.startup_sequence()

    def close(self) -> None:
        for can in self.cans:
            can.close()

    def _safe_ramp_down(self) -> None:
        """Safely ramp down motors (for cleanup callback)."""
        if not self._motors_enabled:
            return
        try:
            self.flush_can_busses()
            self._ramp_down_motors()
        except Exception as e:
            print(f"Error during safe ramp down: {e}")

    def _ramp_down_motors(self) -> None:
        """Gradually ramp down motor torques before disabling (inverse of enable_and_home)."""
        print("Ramping down motors...")
        joint_data = self.get_joint_angles_and_velocities()
        joint_angles: dict[int, float] = {id: data["angle"] for id, data in joint_data.items()}  # type: ignore[misc]
        if len(joint_data) == 0:
            print("No actuators responding, skipping ramp down")
            self._motors_enabled = False
            return

        print(f"Ramping down {len(joint_data)} actuators")
        num_steps = 30
        start_scale = self._last_scaling
        for i in range(num_steps):
            progress = i / (num_steps - 1)
            scale = start_scale * math.exp(math.log(0.001) + (math.log(1.0) - math.log(0.001)) * (1.0 - progress))
            self.set_pd_targets(joint_angles, scaling=scale)
            time.sleep(0.1)

        # Final zero torque command
        self.set_pd_targets(joint_angles, scaling=0.0)
        self._motors_enabled = False
        print("Motors ramped down to zero")

    def startup_sequence(self) -> None:
        if len(self.cans) == 0:
            print("\033[1;31mERROR: No actuators detected\033[0m")
            sys.exit(1)

        joint_data_dict = self.get_joint_angles_and_velocities()

        print("\nActuator states:")
        print("ID  | Name                     | Angle | Velocity | Torque | Temp  | Faults")
        print("----|--------------------------|-------|----------|--------|-------|-------")
        for act_id, data in joint_data_dict.items():
            fault_color = "\033[1;31m" if data["fault_flags"] > 0 else "\033[1;32m"  # type: ignore[operator]
            print(
                f"{act_id:3d} | {data['name']:24s} | {data['angle']:5.2f} | {data['velocity']:8.2f} | "
                f"{data['torque']:6.2f} | {data['temperature']:5.1f} | {fault_color}{data['fault_flags']:3d}\033[0m"
            )
            if data["fault_flags"] > 0:  # type: ignore[operator]
                print("\033[1;33mWARNING: Actuator faults detected\033[0m")

        if any(abs(data["angle"]) > 2.0 for data in joint_data_dict.values()):  # type: ignore[arg-type]
            print("\033[1;31mERROR: Actuator angles too far from zero - move joints closer to home position\033[0m")
            sys.exit(1)

    def enable_and_home_motors(self) -> None:
        for can in self.cans:
            can.enable_motors()
        self._motors_enabled = True
        print("✅ Motors enabled")

        print("\nHoming...")
        home_targets = {id: self.robot.actuators[id].joint_bias for id in self.robot.actuators.keys()}
        for i in range(30):
            scale = math.exp(math.log(0.001) + (math.log(1.0) - math.log(0.001)) * i / 29) * self.max_scaling
            print(f"PD ramp: {scale:.3f}")
            self.set_pd_targets(home_targets, scaling=scale)
            time.sleep(0.1)
        print("✅ Homing complete")

    def get_actuator_feedback(self) -> dict[int, dict[str, int]]:
        fb = {}
        for can in self.cans:
            fb.update(can.get_actuator_feedback())
        return fb

    def sine_wave(self) -> None:
        """Run a sine wave motion on all actuators."""
        t0 = time.perf_counter()
        while True:
            t = time.perf_counter()
            _ = self.get_actuator_feedback()
            t1 = time.perf_counter()
            angle = 0.3 * math.sin(2 * math.pi * 0.5 * (t - t0))
            action = {id: angle + self.robot.actuators[id].joint_bias for id in self.robot.actuators.keys()}
            t2 = time.perf_counter()
            self.set_pd_targets(action, scaling=self.max_scaling)
            t3 = time.perf_counter()
            for can in self.cans:
                can.flush_can_busses()
            self.flush_can_busses()
            t4 = time.perf_counter()
            print(
                f"get feedback={(t1 - t) * 1e6:.0f}us, "
                f"set targets={(t3 - t2) * 1e6:.0f}us, "
                f"receive missing responses={(t4 - t3) * 1e6:.0f}us"
            )
            time.sleep(max(0.02 - (time.perf_counter() - t), 0))

    def set_pd_targets(self, actions: dict[int, float], scaling: float) -> None:
        self._last_scaling = scaling
        for can in self.cans:
            can.set_pd_targets(actions, scaling=scaling)

    def flush_can_busses(self) -> None:
        for can in self.cans:
            can.flush_can_busses()

    def get_joint_angles_and_velocities(self) -> dict[int, dict[str, float | str | int]]:
        answer: dict[int, dict[str, float | str | int]] = {}
        fb = self.get_actuator_feedback()
        for can in self.cans:
            for actuator in can.active_actuators:
                if actuator.can_id in fb:
                    answer[id] = actuator.can_to_physical_data(fb[id])
                    self.last_known_feedback[id] = answer[id].copy()
                elif id in self.last_known_feedback:
                    answer[id] = self.last_known_feedback[id].copy()
                else:
                    answer[actuator.can_id] = actuator.dummy_data()

        return answer

    def get_ordered_joint_data(
        self, joint_order: list[str]
    ) -> tuple[list[float], list[float], list[float], list[float]]:
        joint_data_dict = self.get_joint_angles_and_velocities()

        joint_angles_order, joint_vels_order, torques_order, temps_order = [], [], [], []

        for name in joint_order:
            id = self.robot.full_name_to_actuator_id[name]
            joint_data = joint_data_dict[id]
            joint_angles_order.append(joint_data["angle"])
            joint_vels_order.append(joint_data["velocity"])
            torques_order.append(joint_data["torque"])
            temps_order.append(joint_data["temperature"])

        return joint_angles_order, joint_vels_order, torques_order, temps_order  # type: ignore[return-value]

    def take_action(self, action: list[float], joint_order: list[str]) -> None:
        action = {self.robot.full_name_to_actuator_id[name]: action for name, action in zip(joint_order, action)}
        self.set_pd_targets(action, scaling=self.max_scaling)


def main() -> None:
    """Run sine wave test on all actuators."""
    driver = MotorDriver(max_scaling=0.1)
    input("Press Enter to enable motors...")
    driver.enable_and_home_motors()
    input("Press Enter to run sine wave on all actuators...")
    driver.sine_wave()


if __name__ == "__main__":
    main()


# # .recv takes 10-30us if messages are available.
# TODO reset motor after critical fault?
# TODO reset all act upons startup
# # TODO dont die on critical faults?
# upd listener .clip ccmds
