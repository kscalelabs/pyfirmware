"""Main loop to run policy inference and control motors."""

import argparse
import time

from firmware.can import MotorDriver
from firmware.commands.udp_listener import UDPListener
from firmware.launchInterface import KeyboardLaunchInterface
from firmware.shutdown import get_shutdown_manager


def runner(launch_interface: KeyboardLaunchInterface) -> None:
    shutdown_mgr = get_shutdown_manager()

    motor_driver = MotorDriver()

    if not launch_interface.ask_motor_permission():
        print("Motor permission denied, aborting execution")
        return

    motor_driver.enable_and_home_motors()

    launch_policy = launch_interface.launch_policy_permission()
    if not launch_policy:
        print("Policy launch permission denied, aborting execution")
        return

    # initialize command interface last because it can absorb stdin

    command_interface = UDPListener()

    shutdown_mgr.register_cleanup("Command interface", command_interface.stop)

    print("Starting Control...")

    step_id = 0
    while True:
        t = time.perf_counter()

        joint_cmd = command_interface.get_cmd()

        motor_driver.take_action(joint_cmd)

        motor_driver.flush_can_busses()

        step_id += 1
        time.sleep(max(0.01 - (time.perf_counter() - t), 0))  # wait for 50 hz


if __name__ == "__main__":
    launch_interface = KeyboardLaunchInterface()

    runner(launch_interface)
