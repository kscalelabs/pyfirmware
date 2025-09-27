#!/bin/bash

policy="$(realpath $1)"
command_source="${2:-keyboard}"

# bring up can and set max torques per actuator
bash ~/kbot_deployment/scripts/reset_max_torques.sh

# run firmware with policy
sudo -E chrt 80 /home/dpsh/miniconda3/envs/klog/bin/python ../firmware/main.py $policy --command-source $command_source