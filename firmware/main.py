import argparse
import os
import time

import numpy as np
from can import MotorDriver
from logger import Logger
from command_handling.keyboard import Keyboard
from command_handling.udp_listener import UDPListener

from utils import apply_lowpass_filter, get_imu_reader, get_onnx_sessions


def runner(kinfer_path: str, log_dir: str, command_source: str = "keyboard") -> None:
    logger = Logger(log_dir)

    init_session, step_session, metadata = get_onnx_sessions(kinfer_path)
    joint_order = metadata["joint_names"]
    carry = init_session.run(None, {})[0]

    imu_reader = get_imu_reader()

    motor_driver = MotorDriver()
    print("Press Enter to start policy...")
    input()  # wait for user to start policy
    print("🤖 Running policy...")
    command_interface = None
    # Initialize command interface based on source
    if command_source == "keyboard":
        command_interface = Keyboard()
        print("Using keyboard input (WASD for movement, 0 to reset)")
    elif command_source == "udp":
        command_interface = UDPListener(length=18)
        print("Using UDP input on port 10000 (18-element commands)")
    else:
        raise ValueError(f"Unknown command source: {command_source}")

    t0 = time.perf_counter()
    step_id = 0
    while True:
        t, t_us = time.perf_counter(), time.time() * 1e6
        joint_angles, joint_angular_velocities = motor_driver.get_joint_angles_and_velocities(joint_order)
        t1 = time.perf_counter()
        projected_gravity, gyroscope, timestamp = imu_reader.get_projected_gravity_and_gyroscope()
        t2 = time.perf_counter()
        command = np.array(command_interface.get_cmd(), dtype=np.float32)
        t3 = time.perf_counter()

        action, carry = step_session.run(
            None,
            {
                "joint_angles": np.array(joint_angles, dtype=np.float32),
                "joint_angular_velocities": np.array(joint_angular_velocities, dtype=np.float32),
                "projected_gravity": np.array(projected_gravity, dtype=np.float32),
                "gyroscope": np.array(gyroscope, dtype=np.float32),
                "command": command,
                "carry": carry,
            },
        )
        t4 = time.perf_counter()

        motor_driver.take_action(action, joint_order)
        t5 = time.perf_counter()

        dt = time.perf_counter() - t
        logger.log(
            t - t0,
            {
                "step_id": step_id,
                "timestamp_us": t_us,
                "dt_ms": dt * 1000,
                "dt_joints_ms": (t1 - t) * 1000,
                "dt_imu_ms": (t2 - t1) * 1000,
                "dt_keyboard_ms": (t3 - t2) * 1000,
                "dt_step_ms": (t4 - t3) * 1000,
                "dt_action_ms": (t5 - t4) * 1000,
                "joint_angles": joint_angles,
                "joint_vels": joint_angular_velocities,
                "joint_amps": [],  # TODO add
                "joint_torques": [],  # TODO add
                "joint_temps": [],  # TODO add
                "projected_gravity": projected_gravity,
                "gyro": gyroscope,
                "command": command.tolist(),
                "action": action.tolist(),
                "joint_order": joint_order,
            },
        )
        print(
            f"dt={dt * 1000:.2f} ms: get joints={(t1 - t) * 1000:.2f} ms, get imu={(t2 - t1) * 1000:.2f} ms, .step()={(t4 - t3) * 1000:.2f} ms, take action={(t5 - t4) * 1000:.2f} ms"
        )
        step_id += 1
        time.sleep(max(0.020 - (time.perf_counter() - t), 0))  # wait for 50 hz


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("kinfer_path", type=str, help="Path to saved model file")
    parser.add_argument("--command-source", type=str, default="udp", 
                       choices=["keyboard", "udp"], help="Command input source")
    args = parser.parse_args()

    log_path = os.path.join(os.environ.get("KINFER_LOG_PATH"), "kinfer_log.ndjson")
    runner(args.kinfer_path, log_path)
