#!/bin/bash

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


# set setup can interfaces and set max torques
bash ~/kbot_deployment/scripts/reset_max_torques.sh

# run with klog
# klog-deploy --no-wait "sudo -E chrt 80 /home/dpsh/miniconda3/envs/klog/bin/python main.py $policy"

# run standalone
sudo -E chrt 80 /home/dpsh/miniconda3/envs/klog/bin/python main.py "$policy" "${HOME}/kinfer-logs"

