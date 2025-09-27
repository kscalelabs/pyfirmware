#!/bin/bash

# Parse command line arguments
gstreamer=false
command_source="keyboard"
while [[ $# -gt 0 ]]; do
    case $1 in
        --gstreamer)
            gstreamer=true
            shift
            ;;
        --command-source)
            command_source="$2"
            shift 2
            ;;
        *)
            echo "Unknown option $1"
            echo "Usage: $0 [--gstreamer] [--command-source keyboard|udp]"
            exit 1
            ;;
    esac
done

# check if klog-deploy is installed
if ! [ $(which klog-deploy) ]; then
    echo "klog-deploy not found, please install klog-robot package"
    exit 1
fi

# download kinfer model
policy_dir="${HOME}/.policies"
remote_policies="mu:~/kodachrome/policies/"

mkdir -p "$policy_dir"
rsync -aLP --ignore-existing "$remote_policies" "$policy_dir/"

# user select kinfer model
policy="$policy_dir/$(find "$policy_dir" -maxdepth 1 -type f -printf "%T@ %f\n" | sort -nr | cut -d' ' -f2- | fzf --prompt 'Policy to deploy: ' --height 20% --reverse)"

if [ -z $policy ]; then
    echo "No policy selected."
fi

echo "Deploying policy: $policy"

# run with klog
if [ "$gstreamer" = "true" ]; then
    # start gstreamer in background first
    echo "Starting GStreamer with --flip using webrtc-env"
    sudo -E chrt 80 /home/dpsh/webrtc-pi-env/bin/python "$(dirname "$(realpath "$0")")/../firmware/gstreamer.py" --flip > /dev/null 2>&1 &
    gstreamer_pid=$!
    
    # run main firmware
    klog-deploy --no-wait "$(dirname "$(realpath "$0")")/_run.sh" "$policy" "$command_source"
    
    # kill gstreamer when done
    echo "Stopping GStreamer (PID: $gstreamer_pid)"
    kill $gstreamer_pid 2>/dev/null
else
    # run main firmware only
    klog-deploy --no-wait "$(dirname "$(realpath "$0")")/_run.sh" "$policy" "$command_source"
fi

