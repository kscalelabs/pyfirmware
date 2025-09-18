#!/bin/bash

set -e

# Check for root privileges
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

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
        echo ""
    fi
done
