#!/bin/bash

policy="$(realpath $1)"
command_source="${2:-keyboard}"

# bring up can and set max torques per actuator
bash "$(dirname "$(realpath "$0")")/_set_can_and_max_torques.sh"

# run firmware with policy
sudo -E chrt 80 python -m firmware.main "$policy" --command-source "$command_source"


