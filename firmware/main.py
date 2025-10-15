"""Main loop to run policy inference and control motors."""

import asyncio
import datetime
import os
import time

import numpy as np

from firmware.can import MotorDriver
from firmware.commands.keyboard import Keyboard
from firmware.commands.udp_listener import UDPListener
from firmware.imu.dummy import DummyIMU
from firmware.launchInterface import KeyboardLaunchInterface
from firmware.logger import Logger
from firmware.shutdown import get_shutdown_manager
from firmware.utils import get_imu_reader, get_onnx_sessions


async def runner(kinfer_path: str, launch_interface: KeyboardLaunchInterface, logger: Logger) -> None:
    shutdown_mgr = get_shutdown_manager()


    init_session, step_session, metadata = get_onnx_sessions(kinfer_path)
    joint_order = metadata.get("joint_names", None)
    command_names = metadata.get("command_names", [])
    carry = init_session.run(None, {})[0]

    command_source = await launch_interface.get_command_source()
    print(f"Command source selected: {command_source}")

    command_interface = Keyboard(command_names) if command_source == "keyboard" else UDPListener(command_names)
    shutdown_mgr.register_cleanup("Command interface", command_interface.stop)

    motor_driver = MotorDriver()
    actuator_info = motor_driver.can.actuators

    imu_reader = get_imu_reader()

    if not await launch_interface.ask_motor_permission({"actuator_info": actuator_info, "imu_reader": imu_reader}):
        print("Motor permission denied, aborting execution")
        return

    if imu_reader is None:
        imu_reader = DummyIMU()

    motor_driver.enable_and_home_motors()

    launch_policy = await launch_interface.launch_policy_permission()
    if not launch_policy:
        print("Policy launch permission denied, aborting execution")
        return

    print("Starting policy execution")

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

async def main() -> None:
    launch_interface = KeyboardLaunchInterface()
    kinfer_path = await launch_interface.get_kinfer_path()
    if not kinfer_path:
        print("No kinfer selected or aborted")
        return

    policy_name = os.path.splitext(os.path.basename(kinfer_path))[0]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.expanduser(f"~/kinfer-logs/{policy_name}_{timestamp}")

    print(f"Selected policy: {policy_name}")
    logger = Logger(log_dir)
    await runner(kinfer_path, launch_interface, logger)

if __name__ == "__main__":
    asyncio.run(main())
