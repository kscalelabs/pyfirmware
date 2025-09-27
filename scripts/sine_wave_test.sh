#!/usr/bin/env bash

echo "Running sine wave test to test actuators and CAN bus on 10% pd gains..."

# bring up can and set max torques per actuator
bash "$(dirname "$(realpath "$0")")/_set_can_and_max_torques.sh"

# run sine wave test
/home/dpsh/miniconda3/envs/klog/bin/python "$(dirname "$(realpath "$0")")/../firmware/can.py"
