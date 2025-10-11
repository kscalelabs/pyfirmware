#!/usr/bin/env bash

set -euo pipefail

# download kinfer models (rsync remote -> local cache)
policy_dir="${HOME}/.policies"
remote_policies="mu:~/kodachrome/policies/"

mkdir -p "$policy_dir"
rsync -aLP --ignore-existing "$remote_policies" "$policy_dir/"
