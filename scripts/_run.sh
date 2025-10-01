#!/bin/bash

policy="$(realpath $1)"
command_source="${2:-keyboard}"

# bring up can and set max torques per actuator
bash "$(dirname "$(realpath "$0")")/_set_can_and_max_torques.sh"

# run firmware with policy
if command -v conda >/dev/null 2>&1 && conda env list | awk '{print $1}' | grep -qx firmware; then
    conda run -n firmware python -m firmware.main "$policy" --command-source "$command_source" &
else
    PY="$(command -v python || command -v python3)"
    "$PY" -m firmware.main "$policy" --command-source "$command_source" &
fi
app_pid=$!
if command -v chrt >/dev/null 2>&1; then
    sudo -E chrt -f -p 80 "$app_pid" || true
fi
wait "$app_pid"


