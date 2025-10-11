"""Main loop to run policy inference and control motors."""

import argparse
import asyncio
import datetime
import math
import os
import signal
import sys
import time

import numpy as np

from firmware.can import MotorDriver
from firmware.commands.keyboard import Keyboard
from firmware.commands.udp_listener import UDPListener
from firmware.launchInterface import KeyboardLaunchInterface, WebSocketInterface
from firmware.logger import Logger
from firmware.utils import get_imu_reader, get_onnx_sessions
from firmware.utils import DummyIMU


# Global shutdown flag and interface reference
shutdown_requested = False
launch_interface_ref = None


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global shutdown_requested, launch_interface_ref
    print(f"\n⚠️  Received signal {signum}, initiating shutdown...")
    shutdown_requested = True
    
    # Immediately close the server if it exists
    if launch_interface_ref is not None:
        try:
            # Close the server synchronously
            if hasattr(launch_interface_ref, 'server') and launch_interface_ref.server:
                print("🛑 Force closing WebSocket server...")
                launch_interface_ref.server.close()
        except Exception as e:
            print(f"⚠️  Error in signal handler cleanup: {e}")

def ramp_down_motors(motor_driver: MotorDriver) -> None:
    """Gradually ramp down motor torques before disabling (inverse of enable_and_home)."""
    print("\n🔽 Ramping down motors...")
    try:
        # Get current positions as targets
        home_targets = {id: motor_driver.robot.actuators[id].joint_bias for id in motor_driver.robot.actuators.keys()}
        
        # Ramp down from current scaling to 0 (reverse of ramp up)
        for scale in reversed([math.exp(math.log(0.001) + (math.log(1.0) - math.log(0.001)) * i / 49) for i in range(50)]):
            if scale > motor_driver.max_scaling:
                continue
            print(f"PD ramp down: {scale:.3f}")
            motor_driver.can.set_pd_targets(home_targets, robotcfg=motor_driver.robot, scaling=scale)
            time.sleep(0.1)  # Slower ramp down for safety
        
        # Final zero torque command
        motor_driver.can.set_pd_targets(home_targets, robotcfg=motor_driver.robot, scaling=0.0)
        print("✅ Motors ramped down")
    except Exception as e:
        print(f"⚠️  Error during motor ramp down: {e}")


async def runner(kinfer_path: str, log_dir: str, launchInterface) -> None:
    global shutdown_requested
    
    logger = Logger(log_dir)
    motor_driver = None

    try:
        # Set up command interface
        init_session, step_session, metadata = get_onnx_sessions(kinfer_path)
        joint_order = metadata["joint_names"]
        command_names = metadata["command_names"]
        carry = init_session.run(None, {})[0]

        command_source = await launchInterface.getCommandSource()
        if command_source == "keyboard":
            command_interface = Keyboard(command_names) 
        else:
            if len(command_names) > 0:
                command_interface = UDPListener(command_names)
            else:
                command_interface = UDPListener()

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
        while not shutdown_requested:
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
    
    finally:
        # Always cleanup motors on exit
        if motor_driver is not None:
            print("\n🛑 Cleaning up...")
            ramp_down_motors(motor_driver)
            print("✅ Cleanup complete")


async def main(use_websocket: bool = False):
    """Main entry point that sets up launch interface and runs the policy."""
    global shutdown_requested, launch_interface_ref
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    print("✅ Signal handlers registered (SIGTERM, SIGINT)")
    
    launchInterface = None
    try:
        if use_websocket:
            print("🌐 Using WebSocket interface...")
            launchInterface = await WebSocketInterface.create()
            launch_interface_ref = launchInterface  # Store global reference for signal handler
        else:
            print("⌨️  Using keyboard interface...")
            launchInterface = KeyboardLaunchInterface()
            launch_interface_ref = launchInterface
        
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
            shutdown_requested = True
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if launchInterface is not None:
            print("Closing interface...")
            try:
                await launchInterface.close()
                print("✅ Interface closed")
            except Exception as e:
                print(f"⚠️  Error closing interface: {e}")
        
        # Clear global reference
        launch_interface_ref = None
        print("👋 Shutdown complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run robot firmware with policy inference")
    parser.add_argument(
        "--websocket",
        action="store_true",
        help="Use WebSocket interface instead of keyboard (default: keyboard)"
    )
    args = parser.parse_args()
    
    try:
        asyncio.run(main(use_websocket=args.websocket))
    except KeyboardInterrupt:
        print("\n👋 Interrupted by user")
    finally:
        # Ensure process exits cleanly, releasing all resources including ports
        sys.exit(0)
