#!/usr/bin/env bash
set -euo pipefail

# Usage: scripts/setup-conda.sh [ENV_NAME]
# Default ENV_NAME is "firmware"

ENV_NAME="${1:-firmware}"

# Detect conda
if ! command -v conda >/dev/null 2>&1; then
  echo "Conda not found. Please install Miniconda or Mambaforge." >&2
  exit 1
fi

# Ensure we can call conda in non-interactive shells
eval "$(conda shell.bash hook)"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"

if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
  echo "Updating existing env: ${ENV_NAME}"
  conda env update -n "${ENV_NAME}" -f "${PROJECT_DIR}/environment.yml" --prune -y
else
  echo "Creating env: ${ENV_NAME}"
  conda env create -n "${ENV_NAME}" -f "${PROJECT_DIR}/environment.yml" -y
fi

echo "Conda environment '${ENV_NAME}' is ready. Activate with: conda activate ${ENV_NAME}"

