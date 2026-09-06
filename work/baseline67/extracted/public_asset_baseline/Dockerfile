# The released container is Linux-first because Hunyuan's CUDA rasterizer is not
# portable to macOS/Windows. The core primitive/validation path remains portable.
FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    MUJOCO_GL=egl

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ffmpeg libegl1 libgl1 libglib2.0-0 python3.10 python3.10-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/public_asset_baseline
COPY pyproject.toml requirements-gpu.txt ./
COPY src ./src
COPY config ./config
COPY scripts ./scripts
RUN python3.10 -m pip install --upgrade pip \
    && python3.10 -m pip install --index-url https://download.pytorch.org/whl/cu124 torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
    && python3.10 -m pip install -r requirements-gpu.txt \
    && python3.10 -m pip install .

ENTRYPOINT ["asset-baseline"]
CMD ["--help"]
