#!/usr/bin/env bash
set -euo pipefail

# Usage: DATA_DIR=/absolute/path/to/official_zips OUT_DIR=/absolute/path/to/output ./scripts/run_aliyun.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
: "${DATA_DIR:?set DATA_DIR to a directory containing question.zip and submission_example.zip}"
: "${OUT_DIR:?set OUT_DIR to a writable output directory}"
: "${ACCEPT_HUNYUAN_LICENSE:?read Tencent-Hunyuan/Hunyuan3D-2.1 LICENSE and set ACCEPT_HUNYUAN_LICENSE=yes if your use is allowed}"

if [[ "$ACCEPT_HUNYUAN_LICENSE" != "yes" ]]; then
  echo "ACCEPT_HUNYUAN_LICENSE must be exactly yes" >&2
  exit 2
fi

if [[ ! -f "$DATA_DIR/question.zip" || ! -f "$DATA_DIR/submission_example.zip" ]]; then
  echo "DATA_DIR must contain both official ZIP inputs" >&2
  exit 2
fi
mkdir -p "$OUT_DIR"
if [[ -e "$OUT_DIR/gpu_asset_run" || -e "$OUT_DIR/asset_baseline_submission.zip" ]]; then
  echo "OUT_DIR already contains a GPU run or submission; use a new empty output directory" >&2
  exit 2
fi

(
  cd "$PROJECT_DIR"
  bash infra/verify_gpu_host.sh
)

mkdir -p "$PROJECT_DIR/third_party"
docker build -t public-asset-baseline:latest "$PROJECT_DIR"
docker run --rm --gpus all \
  -v "$DATA_DIR:/data:ro" \
  -v "$OUT_DIR:/output" \
  -v "$PROJECT_DIR/third_party:/opt/public_asset_baseline/third_party" \
  --entrypoint python3.10 public-asset-baseline:latest scripts/run_aliyun_entrypoint.py \
    --question /data/question.zip \
    --submission-example /data/submission_example.zip \
    --output-root /output \
    --run-name gpu_asset_run \
    --accept-hunyuan-license
