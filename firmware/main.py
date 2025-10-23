"""Main loop to run policy inference and control motors."""

import argparse
import datetime
import os
import sys
import time

import numpy as np

from firmware.commands.command_interface import CommandInterface
from firmware.commands.keyboard import Keyboard
from firmware.commands.udp_listener import UDPListener
from firmware.driver import MotorDriver
from firmware.launchInterface import KeyboardLaunchInterface, LaunchInterface, WebSocketLaunchInterface
from firmware.logger import Logger
from firmware.shutdown import get_shutdown_manager
from firmware.utils import get_imu_reader, get_onnx_sessions


def runner(kinfer_path: str, launch_interface: LaunchInterface, logger: Logger) -> None:
    shutdown_mgr = get_shutdown_manager()

    init_session, step_session, metadata = get_onnx_sessions(kinfer_path)
    carry = init_session.run(None, {})[0]

    joint_order = metadata["joint_names"]
    command_names = metadata["command_names"]
    joint_biases = metadata.get("joint_biases", [])
    home_positions = {name: bias for name, bias in zip(joint_order, joint_biases)}

    command_source = launch_interface.get_command_source()

    motor_driver = MotorDriver(home_positions=home_positions)
    imu_reader = get_imu_reader()

    device_data = {
        "actuators": motor_driver.startup_sequence(),
        "imu": imu_reader.imu_name,
    }

    if not launch_interface.ask_motor_permission(device_data):
        print("Motor permission denied, aborting execution")
        return

    motor_driver.enable_and_home_motors()

    launch_policy = launch_interface.launch_policy_permission(policy_name)
    if not launch_policy:
        print("Policy launch permission denied, aborting execution")
        return

    # initialize command interface last because it can absorb stdin
    command_interface: CommandInterface
    if command_source == "keyboard":
        command_interface = Keyboard(command_names)
    else:
        command_interface = UDPListener(command_names, joint_names=joint_order)

    launch_interface.stop()
    del launch_interface
    shutdown_mgr.register_cleanup("Command interface", command_interface.stop)

    print("Starting policy...")

    t0 = time.perf_counter()
    step_id = 0
    while True:
        t, tt = time.perf_counter(), time.time()
        joint_angles, joint_vels, torques, temps = motor_driver.get_ordered_joint_data(joint_order)
        t1 = time.perf_counter()
        projected_gravity, gyroscope, timestamp = imu_reader.get_projected_gravity_and_gyroscope()
        t2 = time.perf_counter()
        policy_cmd, joint_cmd = command_interface.get_cmd()
        t3 = time.perf_counter()

        action, carry = step_session.run(
            None,
            {
                "joint_angles": np.array(joint_angles, dtype=np.float32),
                "joint_angular_velocities": np.array(joint_vels, dtype=np.float32),
                "projected_gravity": np.array(projected_gravity, dtype=np.float32),
                "gyroscope": np.array(gyroscope, dtype=np.float32),
                "command": np.array([v for v in policy_cmd.values()], dtype=np.float32),
                "carry": carry,
            },
        )
        t4 = time.perf_counter()

        # named_action = {joint_name: action for joint_name, action in zip(joint_order, action)} | joint_cmd
        # motor_driver.take_action(named_action)
        t5 = time.perf_counter()
        motor_driver.flush_can_busses()
        t6 = time.perf_counter()

        dt = time.perf_counter() - t
        logger.log(
            t - t0,
            {
                "step_id": step_id,
                "timestamp": tt,
                "dt_ms": dt * 1000,
                "dt_roundtrip_ms": (t5 - t) * 1000,
                "dt_joints_ms": (t1 - t) * 1000,
                "dt_imu_ms": (t2 - t1) * 1000,
                "dt_keyboard_ms": (t3 - t2) * 1000,
                "dt_step_ms": (t4 - t3) * 1000,
                "dt_action_ms": (t5 - t4) * 1000,
                "dt_flush_can_busses_ms": (t6 - t5) * 1000,
                "joint_angles": joint_angles,
                "joint_velocities": joint_vels,
                # "joint_amps": [],  # TODO add
                "joint_torques": torques,
                "joint_temps": temps,
                "projected_gravity": projected_gravity,
                "gyroscope": gyroscope,
                "command": policy_cmd | joint_cmd,
                "action": action.tolist(),
                "joint_order": joint_order,
            },
        )
        print(
            f"dt={dt * 1000:.2f} ms: "
            f"get joints={(t1 - t) * 1000:.2f} ms, "
            f"get imu={(t2 - t1) * 1000:.2f} ms, "
            f".step()={(t4 - t3) * 1000:.2f} ms, "
            f"take action={(t5 - t4) * 1000:.2f} ms, "
            f"flush can={(t6 - t5) * 1000:.2f} ms"
        )
        step_id += 1
        time.sleep(max(0.020 - (time.perf_counter() - t), 0))  # wait for 50 hz


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run policy inference and control motors")
    parser.add_argument("policy_dir", help="Policy directory path (required)")
    parser.add_argument("--websocket", action="store_true", help="Use WebSocket interface instead of keyboard")
    args = parser.parse_args()


    launch_interface = WebSocketLaunchInterface() if args.websocket else KeyboardLaunchInterface()

    kinfer_path = launch_interface.get_kinfer_path(args.policy_dir)

    if kinfer_path is None:
        print("No policy selected. Exiting.")
        sys.exit(1)

    policy_name = os.path.splitext(os.path.basename(kinfer_path))[0]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.expanduser(f"~/kinfer-logs/{policy_name}_{timestamp}")

    print(f"Selected policy: {policy_name}")
    logger = Logger(log_dir)
    runner(kinfer_path, launch_interface, logger)
