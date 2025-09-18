#!/bin/bash

set -e

# Function to confirm with user before taking an action
confirm_action() {
    if [ "$@" -ne 2 ]; then
        echo "Usage: confirm_action <prompt> <action>"
        return 1
    fi

    local prompt="$1"
    local action="$2"

    if read -p "$prompt (y/n) " -n 1 -r; then
        if [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]; then
            eval "$action"
            return 0
        fi
    fi
    echo
    return 1
}

# ------------------------------------------------
# Kill USB autosuspend and CPI low-power dithering

if [ ! -d /sys/bus/usb/devices ]; then
    echo "Error: /sys/bus/usb/devices directory not found"
    exit 1
fi

for device in /sys/bus/usb/devices/*/power/control; do
    if [ "$(cat $device)" != "on" ]; then
        if read -p "Set $device to on? (y/n) " -n 1 -r; then
            if [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]; then
                echo "on" > $device
            fi
        fi
    fi
done
