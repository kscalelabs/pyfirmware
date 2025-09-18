#!/bin/sh

# Check /sys/bus/usb/devices/*/power/control to make sure they are set to "on" instead of "auto"
for device in /sys/bus/usb/devices/*/power/control; do
    if [ "$(cat $device)" != "on" ]; then
        if read -p "Set $device to on? (y/n) " -n 1 -r; then
            echo "on" > $device
        fi
    fi
done
