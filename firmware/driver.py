"""Driver logic for the motor driver."""

import math
import sys
import time

from firmware.actuators import RobotConfig
from firmware.can import CANInterface
from firmware.launchInterface import KeyboardLaunchInterface
from firmware.shutdown import get_shutdown_manager


class MotorDriver:
    """Driver logic."""

    def __init__(self, home_positions: dict[str, float], max_scaling: float = 1.0) -> None:
        self.max_scaling = max_scaling
        self.robot = RobotConfig()

        self.home_positions: dict[int, float] = {}
        for actuator in self.robot.actuators.values():
            self.home_positions[actuator.can_id] = home_positions.get(actuator.full_name, actuator.default_home)

        self.can = CANInterface()
        self.last_known_feedback: dict[int, dict[str, float | str | int]] = {}
        self._motors_enabled = False
        self._last_scaling = 0.0

        shutdown_mgr = get_shutdown_manager()
        shutdown_mgr.register_cleanup("CAN sockets", self.can.close)  # Register first, closes last
        shutdown_mgr.register_cleanup("Motor ramp down", self._safe_ramp_down)  # Register last, executes first


    def _safe_ramp_down(self) -> None:
        """Safely ramp down motors (for cleanup callback)."""
        if not self._motors_enabled:
            return
        try:
            self.flush_can_busses()
            self._ramp_down_motors()
        except Exception as e:
            print(f"Error during safe ramp down: {e}")

        self.can.disable_motors()

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

    def startup_sequence(self) -> dict[int, dict[str, float | str | int]]:
        if not self.can.actuators:
            print("\033[1;31mERROR: No actuators detected\033[0m")
            sys.exit(1)

        joint_data_dict = self.get_joint_angles_and_velocities(zeros_fallback=False)

        if any(abs(data["angle"]) > 2.0 for data in joint_data_dict.values()):  # type: ignore[arg-type]
            print("\033[1;31mERROR: Actuator angles too far from zero - move joints closer to home position\033[0m")
            sys.exit(1)

        return joint_data_dict

    def enable_and_home_motors(self) -> None:
        self.can.enable_motors()
        self._motors_enabled = True
        print("✅ Motors enabled")

        print("\nHoming...")
        for i in range(30):
            scale = math.exp(math.log(0.001) + (math.log(1.0) - math.log(0.001)) * i / 29) * self.max_scaling
            print(f"PD ramp: {scale:.3f}")
            self.set_pd_targets(self.home_positions, scaling=scale)
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
            action = {id: angle + self.home_positions[id] for id in self.robot.actuators.keys()}
            t2 = time.perf_counter()
            self.set_pd_targets(action, scaling=self.max_scaling)
            t3 = time.perf_counter()
            self.can.flush_can_busses()
            t4 = time.perf_counter()
            print(
                f"get feedback={(t1 - t) * 1e6:.0f}us, "
                f"set targets={(t3 - t2) * 1e6:.0f}us, "
                f"receive missing responses={(t4 - t3) * 1e6:.0f}us"
            )
            time.sleep(max(0.02 - (time.perf_counter() - t), 0))

    def set_pd_targets(self, actions: dict[int, float], scaling: float) -> None:
        self._last_scaling = scaling
        self.can.set_pd_targets(actions, robotcfg=self.robot, scaling=scaling)

    def flush_can_busses(self) -> None:
        self.can.flush_can_busses()

    def get_joint_angles_and_velocities(self, zeros_fallback: bool = True) -> dict[int, dict[str, float | str | int]]:
        fb = self.can.get_actuator_feedback()
        answer: dict[int, dict[str, float | str | int]] = {}
        for id in self.robot.actuators.keys():
            if id in fb:
                answer[id] = self.robot.actuators[id].can_to_physical_data(fb[id])
                self.last_known_feedback[id] = answer[id].copy()
            elif id in self.last_known_feedback:  # Fallback to last known good values
                answer[id] = self.last_known_feedback[id].copy()
            elif zeros_fallback:  # Fallback to zeros for unknown actuators
                answer[id] = self.robot.actuators[id].dummy_data()
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

    def take_action(self, actions: dict[str, float]) -> None:
        action = {self.robot.full_name_to_actuator_id[name]: action for name, action in actions.items()}
        self.set_pd_targets(action, scaling=self.max_scaling)


def main() -> None:
    """Run sine wave test on all actuators."""
    driver = MotorDriver(dict(), max_scaling=0.1)
    launch_interface = KeyboardLaunchInterface()

    device_data = {"actuators": driver.startup_sequence()}

    if not launch_interface.ask_motor_permission(device_data):
        sys.exit(1)
    driver.enable_and_home_motors()

    if not launch_interface.launch_policy_permission("sine_wave"):
        sys.exit(1)

    driver.sine_wave()


if __name__ == "__main__":
    main()


# # .recv takes 10-30us if messages are available.
# TODO reset motor after critical fault?
# TODO reset all act upons startup
# # TODO dont die on critical faults?
# upd listener .clip ccmds
