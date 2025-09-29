#!/usr/bin/env bash

selected="$*"

declare -A actuators=(
    [11]="Lsp"
    [12]="Lsr"
    [13]="Lsy"
    [14]="Lep"
    [15]="Lwr"
    [16]="Lwy"
    [17]="Lwp"
    [21]="Rsp"
    [22]="Rsr"
    [23]="Rsy"
    [24]="Rep"
    [25]="Rwr"
    [26]="Rwy"
    [27]="Rwp"
    [31]="Lhp"
    [32]="Lhr"
    [33]="Lhy"
    [34]="Lkp"
    [35]="Lap"
    [41]="Rhp"
    [42]="Rhr"
    [43]="Rhy"
    [44]="Rkp"
    [45]="Rap"
)

declare -A max_torques=(
     [11]=42.0
     [12]=42.0
     [13]=11.9
     [14]=11.9
     [15]=9.8
     [16]=9.8
     [17]=9.8
     [21]=42.0
     [22]=42.0
     [23]=11.9
     [24]=11.9
     [25]=9.8
     [26]=9.8
     [27]=9.8
     [31]=84.0
     [32]=42.0
     [33]=42.0
     [34]=84.0
     [35]=11.9
     [41]=84.0
     [42]=42.0
     [43]=42.0
     [44]=84.0
     [45]=11.9
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
	    echo "Set max_torque to $(printf "%04.1f" "$val") on actuator $id_dec (${actuators[$id_dec]}): $resp"
	    last_iface="$interface"
            break
        fi
    done

    if [ -z "$resp" ]; then
        echo "No response from actuator $id_dec (${actuators[$id_dec]})"
    fi
done
