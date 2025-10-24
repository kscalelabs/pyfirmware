"""Driver logic for the motor driver."""

import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from firmware.actuators import RobotConfig
from firmware.can import CANInterface
from firmware.launchInterface import KeyboardLaunchInterface
from firmware.shutdown import get_shutdown_manager

CANBUS_RANGE = range(0, 7)

class MotorDriver:
    def __init__(self, home_positions: dict[str, float], max_scaling: float = 1.0) -> None:
        self.max_scaling = max_scaling
        self.robot = RobotConfig()
        self.cans: list[CANInterface] = []

        print("\033[1;36m Initializing CAN buses...\033[0m")
        for canbus in CANBUS_RANGE:
            try:
                can_interface = CANInterface(self.robot, canbus)
                if len(can_interface.pings_actuators) > 0:
                    self.cans.append(can_interface)
                else:
                    can_interface.close()
            except Exception as e:
                print(f"\033[1;33mWARNING: Failed to initialize CAN{canbus}: {e}\033[0m")

        if not self.cans:
            print("\033[1;31mERROR: No CAN buses initialized successfully\033[0m")
            sys.exit(1)

        self.coordinator_executor = ThreadPoolExecutor(
            max_workers=len(self.cans),
            thread_name_prefix="coordinator"
        )

        total_actuators = sum(len(can.pings_actuators) for can in self.cans)
        print(f"\033[1;32m✓ Initialized {len(self.cans)} buses with {total_actuators} total actuators\033[0m")

        self.home_positions: dict[int, float] = {}
        for actuator in self.robot.actuators.values():
            self.home_positions[actuator.can_id] = home_positions.get(actuator.full_name, actuator.default_home)

        self._motors_enabled = False
        self._last_scaling = 0.0

        shutdown_mgr = get_shutdown_manager()
        shutdown_mgr.register_cleanup("CAN sockets", self._cleanup_cans)
        shutdown_mgr.register_cleanup("Motor ramp down", self._safe_ramp_down)

    def async_can(
        self, func_name: str, *args: object, timeout: float = 0.1, wait_for_response: bool = True
    ) -> Dict[str, Any]:
        futures = []
        for i, can in enumerate(self.cans):
            method = getattr(can, func_name)
            future = self.coordinator_executor.submit(method, *args)
            futures.append((i, future))

        if not wait_for_response:
            return {}

        combined_results = {}
        for i, future in futures:
            try:
                result = future.result(timeout=timeout)
                if result is not None:
                    if isinstance(result, dict):
                        combined_results.update(result)
                    else:
                        combined_results[f"can{i}"] = result
            except Exception as e:
                print(f"\033[1;33mWARNING: Error on CAN{i} calling {func_name}: {e}\033[0m")

        return combined_results

    def _cleanup_cans(self) -> None:
        print("\033[1;36m Shutting down can threads...\033[0m")
        self.coordinator_executor.shutdown(wait=True, cancel_futures=True)
        for can in self.cans:
            try:
                can.close()
            except Exception as e:
                print(f"\033[1;31mError closing CAN bus: {e}\033[0m")

        self.cans.clear()
        print("\033[1;32m✓ Motor driver shutdown complete\033[0m")

    def _safe_ramp_down(self) -> None:
        if not self._motors_enabled:
            return
        try:
            self.flush_can_busses()
            self._ramp_down_motors()
        except Exception as e:
            print(f"Error during safe ramp down: {e}")

        self.async_can("disable_motors", timeout=1.0, wait_for_response=True)

    def _ramp_down_motors(self) -> None:
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

        self.set_pd_targets(joint_angles, scaling=0.0)
        self._motors_enabled = False

    def startup_sequence(self) -> dict[int, dict[str, float | str | int]]:
        if len(self.cans) == 0:
            print("\033[1;31mERROR: No actuators detected\033[0m")
            sys.exit(1)

        joint_data_dict = self.get_joint_angles_and_velocities(zeros_fallback=False)
        if any(abs(data["angle"]) > 2.0 for data in joint_data_dict.values()):  # type: ignore[arg-type]
            print("\033[1;31mERROR: Actuator angles too far from zero - move joints closer to home position\033[0m")
            sys.exit(1)

        return joint_data_dict

    def enable_and_home_motors(self) -> None:
        self.async_can("enable_motors", timeout=2.0, wait_for_response=True)

        self._motors_enabled = True
        print("\033[1;32m✓ All motors enabled\033[0m")

        print("\nHoming...")
        for i in range(30):
            scale = math.exp(math.log(0.001) + (math.log(1.0) - math.log(0.001)) * i / 29) * self.max_scaling
            print(f"PD ramp: {scale:.3f}")
            self.set_pd_targets(self.home_positions, scaling=scale)
            time.sleep(0.1)
        print("✅ Homing complete")

    def sine_wave(self) -> None:
        t0 = time.perf_counter()
        while True:
            t = time.perf_counter()
            _ = self.get_joint_angles_and_velocities()
            t1 = time.perf_counter()
            angle = 0.3 * math.sin(2 * math.pi * 0.5 * (t - t0))
            action = {id: angle + self.home_positions[id] for id in self.robot.actuators.keys()}
            t2 = time.perf_counter()
            self.set_pd_targets(action, scaling=self.max_scaling)
            t3 = time.perf_counter()
            flushed = self.flush_can_busses()
            t4 = time.perf_counter()
            print(
                f"get feedback={(t1 - t) * 1e6:.0f}us, "
                f"set targets={(t3 - t2) * 1e6:.0f}us, "
                f"flush={flushed} msgs in {(t4 - t3) * 1e6:.0f}us"
            )
            time.sleep(max(0.02 - (time.perf_counter() - t), 0))

    def set_pd_targets(self, actions: dict[int, float], scaling: float) -> None:
        self._last_scaling = scaling
        self.async_can("set_pd_targets", actions, scaling, timeout=0.05, wait_for_response=False)

    def flush_can_busses(self) -> None:
        self.async_can("flush_can_bus_completely", timeout=0.1, wait_for_response=True)

    def get_joint_angles_and_velocities(self) -> dict[int, dict[str, float | str | int]]:
        return self.async_can("get_actuator_feedback", timeout=0.1, wait_for_response=True)

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
