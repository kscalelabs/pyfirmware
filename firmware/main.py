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
from firmware.logger_general import Logger
from firmware.utils import get_imu_reader, get_onnx_sessions
from firmware.utils import DummyIMU
from firmware.logger import Logger as Logger_run

# Global shutdown flag and interface reference
shutdown_requested = False
launch_interface_ref = None
motor_driver_ref = None
motors_enabled = False


def end_policy():
    """Emergency cleanup function that can be called from signal handlers."""
    global motor_driver_ref, motors_enabled
    try:
        if motor_driver_ref is not None and motors_enabled:
            print("Ramping down motors...")
            motor_driver_ref.ramp_down_motors()
                
    except Exception as e:
        print(f"Error in end_policy: {e}")
    finally:
        # Clear global references
        motor_driver_ref = None
        motors_enabled = False


def signal_handler(signum, frame):
    """Handle shutdown signals with immediate motor safety."""
    global shutdown_requested, launch_interface_ref, motor_driver_ref, motors_enabled
    print(f"\n Received signal {signum}, initiating emergency shutdown...")
    shutdown_requested = True

    end_policy()
    sys.exit(0)

async def runner(kinfer_path: str, log_dir: str, launchInterface) -> None:
    global shutdown_requested, motor_driver_ref, motors_enabled
    
    # Create logger
    logger = Logger(logdir=log_dir, console_level="INFO")
    logger_run = Logger_run(logdir=log_dir)
    motor_driver = None

    try:
        logger.info("Starting robot policy execution", 
                   extra_data={"kinfer_path": kinfer_path, "log_dir": log_dir})
        
        # Set up command interface
        init_session, step_session, metadata = get_onnx_sessions(kinfer_path)
        joint_order = metadata["joint_names"]
        command_names = metadata["command_names"]
        carry = init_session.run(None, {})[0]

        command_source = await launchInterface.get_command_source()
        logger.info(f"Command source selected: {command_source}")
        
        if command_source == "keyboard":
            command_interface = Keyboard(command_names, logger)
            logger.debug("Initialized keyboard command interface")
        else:
            if len(command_names) > 0:
                command_interface = UDPListener(logger, command_names)
            else:
                command_interface = UDPListener(logger)
            logger.debug("Initialized UDP command interface")

        imu_reader = get_imu_reader()
        logger.debug(f"IMU reader initialized: {type(imu_reader).__name__}")
        
        if not await launchInterface.ask_imu_permission(imu_reader):
            logger.warning("IMU permission denied, aborting execution")
            return
            
        if imu_reader is None:
            imu_reader = DummyIMU()
            logger.warning("Using dummy IMU - no real IMU hardware detected")

        
        motor_driver = MotorDriver(logger)
        motor_driver_ref = motor_driver  # Store global reference for signal handler
        logger.debug("Motor driver initialized")
        
        actuator_info = motor_driver.get_actuator_info()
        logger.debug("Retrieved actuator information", extra_data=actuator_info)
        
        start_motors = await launchInterface.ask_motor_permission(actuator_info)
        if not start_motors:
            logger.warning("Motor permission denied, aborting execution")
            return
        motor_driver.enable_and_home()
        motors_enabled = True  # Mark motors as enabled
        logger.info("Motors enabled and homed successfully")
        
        launchPolicy = await launchInterface.launch_policy_permission()
        if not launchPolicy:
            logger.warning("Policy launch permission denied, aborting execution")
            return
            
        logger.info("Starting policy execution")

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
            
            logger_run.log(
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
            logger.debug(
            f"dt={dt * 1000:.2f} ms: get joints={(t1 - t) * 1000:.2f} ms, get imu={(t2 - t1) * 1000:.2f} ms, "
            f".step()={(t4 - t3) * 1000:.2f} ms, take action={(t5 - t4) * 1000:.2f} ms, missing responses={(t6 - t5) * 1000:.2f} ms"
            )

            
            step_id += 1
            time.sleep(max(0.020 - (time.perf_counter() - t), 0))  # wait for 50 hz
    
    except Exception as e:
        # Log the error before cleanup
        logger.error(
            f"Policy execution failed: {str(e)}",
            extra_data={"error_type": type(e).__name__}
        )
        # Always cleanup motors on exit
        end_policy()

async def main(use_websocket: bool = False):
    """Main entry point that sets up launch interface and runs the policy."""
    global shutdown_requested, launch_interface_ref
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    print("✅ Signal handlers registered (SIGTERM, SIGINT)")
    
    # Create a temporary logger for startup messages
    logger = Logger("/tmp", console_level="INFO")
    logger.info(f"Starting robot firmware", extra_data={"use_websocket": use_websocket})
    
    launchInterface = None
    try:
        if use_websocket:
            launchInterface = await WebSocketInterface.create()
            launch_interface_ref = launchInterface  # Store global reference for signal handler
            logger.info("WebSocket interface created successfully")
        else:
            launchInterface = KeyboardLaunchInterface()
            launch_interface_ref = launchInterface
            logger.info("Keyboard interface created successfully")
        
        # Get kinfer path from client/user
        kinfer_path = await launchInterface.get_kinfer_path()
        if not kinfer_path:
            logger.warning("No kinfer selected or aborted")
            return
        
        policy_name = os.path.splitext(os.path.basename(kinfer_path))[0]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = os.path.expanduser(f"~/kinfer-logs/{policy_name}_{timestamp}")
        
        logger.info(f"Selected policy: {policy_name}", extra_data={"kinfer_path": kinfer_path, "log_dir": log_dir})

        try:
            await runner(kinfer_path, log_dir, launchInterface)
        except KeyboardInterrupt:
            logger.info("Shutting down due to keyboard interrupt")
            shutdown_requested = True
    
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", extra_data={"error_type": type(e).__name__})
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