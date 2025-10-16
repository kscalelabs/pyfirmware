"""Main loop to run policy inference and control motors."""

import argparse
import datetime
import os
import time

import numpy as np

from firmware.can import MotorDriver
from firmware.commands.keyboard import Keyboard
from firmware.commands.udp_listener import UDPListener
from firmware.launchInterface import KeyboardLaunchInterface, WebSocketInterface, LaunchInterface
from firmware.logger import Logger
from firmware.shutdown import get_shutdown_manager
from firmware.utils import get_imu_reader, get_onnx_sessions


def runner(kinfer_path: str, launch_interface: LaunchInterface, logger: Logger) -> None:
    shutdown_mgr = get_shutdown_manager()

    init_session, step_session, metadata = get_onnx_sessions(kinfer_path)
    joint_order = metadata.get("joint_names", None)
    command_names = metadata.get("command_names", [])
    carry = init_session.run(None, {})[0]

    command_source = launch_interface.get_command_source()
    motor_driver = MotorDriver()
    imu_reader = get_imu_reader()

    actuator_status = motor_driver.get_actuator_status()
    robot_devices = {"imu": imu_reader, "actuator_status": actuator_status}
    if not launch_interface.ask_motor_permission(robot_devices):
        print("Motor permission denied, aborting execution")
        return

    motor_driver.enable_and_home_motors()

    launch_policy = launch_interface.launch_policy_permission()
    if not launch_policy:
        print("Policy launch permission denied, aborting execution")
        return

    # initialize command interface last because it can absorb stdin
    command_interface = Keyboard(command_names) if command_source == "keyboard" else UDPListener(command_names)
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
        command = command_interface.get_cmd()
        t3 = time.perf_counter()

        action, carry = step_session.run(
            None,
            {
                "joint_angles": np.array(joint_angles, dtype=np.float32),
                "joint_angular_velocities": np.array(joint_vels, dtype=np.float32),
                "projected_gravity": np.array(projected_gravity, dtype=np.float32),
                "gyroscope": np.array(gyroscope, dtype=np.float32),
                "command": np.array(command, dtype=np.float32),
                "carry": carry,
            },
        )
        t4 = time.perf_counter()

        motor_driver.take_action(action, joint_order)
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
                "command": command,
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
    parser.add_argument("--websocket", action="store_true", help="Use WebSocket launch interface")
    args = parser.parse_args()

    launch_interface: LaunchInterface = WebSocketInterface() if args.websocket else KeyboardLaunchInterface()
    kinfer_path = launch_interface.get_kinfer_path(args.policy_dir)
    if kinfer_path is None:
        print("No kinfer path selected, aborting execution")
        exit(0)

    policy_name = os.path.splitext(os.path.basename(kinfer_path))[0]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.expanduser(f"~/kinfer-logs/{policy_name}_{timestamp}")

    print(f"Selected policy: {policy_name}")
    logger = Logger(log_dir)
    runner(kinfer_path, launch_interface, logger)
