#!/usr/bin/env bash
set -euo pipefail

MIN_GPU_MEMORY_MIB="${MIN_GPU_MEMORY_MIB:-45000}"
MIN_FREE_DISK_GIB="${MIN_FREE_DISK_GIB:-200}"

command -v nvidia-smi >/dev/null
command -v docker >/dev/null

GPU_INFO="$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits)"
printf '%s\n' "$GPU_INFO"

MAX_GPU_MEMORY_MIB="$(printf '%s\n' "$GPU_INFO" | awk -F',' '
  { gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); if ($2 + 0 > max) max = $2 + 0 }
  END { print max + 0 }
')"
if (( MAX_GPU_MEMORY_MIB < MIN_GPU_MEMORY_MIB )); then
  echo "Need at least ${MIN_GPU_MEMORY_MIB} MiB GPU memory; detected ${MAX_GPU_MEMORY_MIB} MiB" >&2
  exit 1
fi

FREE_DISK_KIB="$(df -Pk . | awk 'NR == 2 { print $4 }')"
MIN_FREE_DISK_KIB="$((MIN_FREE_DISK_GIB * 1024 * 1024))"
if (( FREE_DISK_KIB < MIN_FREE_DISK_KIB )); then
  echo "Need at least ${MIN_FREE_DISK_GIB} GiB free disk; detected $((FREE_DISK_KIB / 1024 / 1024)) GiB" >&2
  exit 1
fi
echo "Free disk: $((FREE_DISK_KIB / 1024 / 1024)) GiB"

docker --version
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
