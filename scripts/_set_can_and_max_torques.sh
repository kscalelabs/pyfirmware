#!/usr/bin/env bash

selected="$*"

declare -A max_torques=(
    [11]=42.0 [12]=42.0 [13]=11.9 [14]=11.9 [15]=9.8 [16]=9.8 [17]=9.8            # Left arm
    [21]=42.0 [22]=42.0 [23]=11.9 [24]=11.9 [25]=9.8 [26]=9.8 [27]=9.8            # Right arm
)

echo "Setting up CAN interfaces..."

for i in {0..6}; do
    echo "Setting up can$i..."
    sudo ip link set can$i down
    sudo ip link set can$i type can bitrate 1000000
    sudo ip link set can$i txqueuelen 1000
    sudo ip link set can$i up
done

ifaces="$(ip link show | grep -oP 'can[0-9]+' | sort -u)"

selected="$(for i in {1..4}; do for j in {1..7}; do echo $i$j; done; done)"

for id_dec in $selected; do
    id=$(printf "%.2X" "$id_dec")

    val="${max_torques[$id_dec]}"
    val_hex="$(python -c "import numpy; print(numpy.float32($val).tobytes().hex())")"
    val_littleendian="${val_hex:0:2}.${val_hex:2:2}.${val_hex:4:2}.${val_hex:6:2}"

    resp=""

    for interface in $last_iface $ifaces; do
        resp="$(candump  -T 25 $interface,0200${id}FD:0000FF00 & sleep .01;
		cansend $interface 1200FD${id}#0B.70.00.00.${val_littleendian})"
        if [ "$resp" ]; then
	    echo "Set max_torque to $(printf "%04.1f" "$val") on actuator $id_dec: $resp"
	    last_iface="$interface"
            break
        fi
    done

    if [ -z "$resp" ]; then
        echo "No response from actuator $id_dec"
    fi
done
