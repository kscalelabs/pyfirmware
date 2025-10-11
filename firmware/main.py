"""Main loop to run policy inference and control motors."""

import argparse
import asyncio
import datetime
import os
import time

import numpy as np

from firmware.can import MotorDriver
from firmware.commands.keyboard import Keyboard
from firmware.commands.udp_listener import UDPListener
from firmware.launchInterface import KeyboardLaunchInterface, WebSocketInterface
from firmware.logger import Logger
from firmware.utils import get_imu_reader, get_onnx_sessions
from firmware.utils import DummyIMU

async def runner(kinfer_path: str, log_dir: str, launchInterface: WebSocketInterface) -> None:

    logger = Logger(log_dir)

    
    #set up command interface
    init_session, step_session, metadata = get_onnx_sessions(kinfer_path)
    joint_order = metadata["joint_names"]
    command_names = metadata["command_names"]
    command_interface = None
    command_source = await launchInterface.getCommandSource()
    if command_source == "keyboard":
        command_interface = Keyboard(command_names) 
    else:
        if len(command_names) > 0:
            command_interface = UDPListener(command_names)
        else:
            command_interface = UDPListener()

    carry = init_session.run(None, {})[0]

    imu_reader = get_imu_reader()
    if not await launchInterface.askIMUPermission(imu_reader):
        return
    if imu_reader is None:
        imu_reader = DummyIMU()
    
    motor_driver = MotorDriver()
    
    actuator_info = motor_driver.get_actuator_info()
    start_motors = await launchInterface.askMotorPermission(actuator_info)
    if not start_motors:
        print("Start Actuators- User Aborted")
        return
    motor_driver.enable_and_home()
    
    launchPolicy = await launchInterface.launchPolicyPermission()
    if not launchPolicy:
        print("Launch Policy- User Aborted")
        return
    print("🤖 Running policy...")

    

    t0 = time.perf_counter()
    step_id = 0
    while True:
        t, tt = time.perf_counter(), time.time()
        joint_angles, joint_vels, torques, temps = motor_driver.get_joint_angles_and_velocities(joint_order)
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
        motor_driver.receive_missing_responses()
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
                "dt_missing_responses_ms": (t6 - t5) * 1000,
                "joint_angles": joint_angles,
                "joint_vels": joint_vels,
                "joint_amps": [],  # TODO add
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
            f"dt={dt * 1000:.2f} ms: get joints={(t1 - t) * 1000:.2f} ms, get imu={(t2 - t1) * 1000:.2f} ms, "
            f".step()={(t4 - t3) * 1000:.2f} ms, take action={(t5 - t4) * 1000:.2f} ms, missing responses={(t6 - t5) * 1000:.2f} ms"
        )
        step_id += 1
        time.sleep(max(0.020 - (time.perf_counter() - t), 0))  # wait for 50 hz


async def main(use_websocket: bool = False):
    """Main entry point that sets up launch interface and runs the policy."""
    
    # Choose launch interface based on argument
    launchInterface = None
    if use_websocket:
        print("🌐 Using WebSocket interface...")
        launchInterface = await WebSocketInterface.create()
    else:
        print("⌨️  Using keyboard interface...")
        launchInterface = KeyboardLaunchInterface()
    
    try:
        # Get kinfer path from client/user
        kinfer_path = await launchInterface.getKinferPath()
        if not kinfer_path:
            print("No kinfer selected or aborted")
            return
        
        policy_name = os.path.splitext(os.path.basename(kinfer_path))[0]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = os.path.expanduser(f"~/kinfer-logs/{policy_name}_{timestamp}")

        try:
            await runner(kinfer_path, log_dir, launchInterface)
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
    finally:
        print("Closing interface...")
        await launchInterface.close()
        print("✅ Interface closed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run robot firmware with policy inference")
    parser.add_argument(
        "--websocket",
        action="store_true",
        help="Use WebSocket interface instead of keyboard (default: keyboard)"
    )
    args = parser.parse_args()
    
    asyncio.run(main(use_websocket=args.websocket))
