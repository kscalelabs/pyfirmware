"""Main loop to run policy inference and control motors."""

import argparse
import datetime
import os
import time

import numpy as np

from firmware.can import MotorDriver
from firmware.commands.keyboard import Keyboard
from firmware.commands.udp_listener import UDPListener
from firmware.logger import Logger
from firmware.utils import get_imu_reader, get_onnx_sessions
import signal
import sys

motor_driver_ref = None
motors_enabled = False
command_interface_ref = None


def signal_handler(signum, frame):
    end_policy()
    sys.exit(0)

def end_policy():
    """Cleanup function that should be called to safely shutdown the policy."""
    global motor_driver_ref, motors_enabled, command_interface_ref
    try:
        # Stop command interface
        if command_interface_ref is not None:
            command_interface_ref.stop()
        if motors_enabled and motor_driver_ref is not None:
            motor_driver_ref.ramp_down_motors()
    except Exception as e:
        print(f"❌ Error in end_policy: {e}")
    finally:
        # Clear global references
        motor_driver_ref = None
        motors_enabled = False
        command_interface_ref = None
        
def runner(kinfer_path: str, log_dir: str, command_source: str = "keyboard") -> None:
    global motor_driver_ref, motors_enabled, command_interface_ref
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger = Logger(log_dir)

    init_session, step_session, metadata = get_onnx_sessions(kinfer_path)
    joint_order = metadata["joint_names"]
    command_names = metadata["command_names"]
    carry = init_session.run(None, {})[0]

    imu_reader = get_imu_reader()

    motor_driver = MotorDriver()
    motor_driver_ref = motor_driver
    motors_enabled = True
    
    print("Press Enter to start policy...")
    input()  # wait for user to start policy
    print("🤖 Running policy...")

    command_interface = Keyboard(command_names) if command_source == "keyboard" else UDPListener(command_names)
    command_interface_ref = command_interface

    try:
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
                f"dt={dt * 1000:.2f} ms: get joints={(t1 - t) * 1000:.2f} ms, "
                f"get imu={(t2 - t1) * 1000:.2f} ms, "
                f".step()={(t4 - t3) * 1000:.2f} ms, "
                f"take action={(t5 - t4) * 1000:.2f} ms, "
                f"missing responses={(t6 - t5) * 1000:.2f} ms"
            )
            step_id += 1
            time.sleep(max(0.020 - (time.perf_counter() - t), 0))  # wait for 50 hz
    except Exception as e:
        print(f"❌ Error in runner: {e}")
        end_policy()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("kinfer_path", type=str, help="Path to saved model file")
    parser.add_argument(
        "--command-source", type=str, default="keyboard", choices=["keyboard", "udp"], help="Command input source"
    )
    args = parser.parse_args()

    policy_name = os.path.splitext(os.path.basename(args.kinfer_path))[0]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.expanduser(f"~/kinfer-logs/{policy_name}_{timestamp}")

    runner(args.kinfer_path, log_dir, args.command_source)
