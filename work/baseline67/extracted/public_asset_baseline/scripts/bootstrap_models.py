#!/usr/bin/env python3
"""Fetch only pinned public code; competition ZIPs are never uploaded by this tool."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import urllib.request
from pathlib import Path


SAM2_REPOSITORY = "https://github.com/facebookresearch/sam2.git"
SAM2_COMMIT = "2b90b9f5ceec907a1c18123530e92e794ad901a4"
HUNYUAN_REPOSITORY = "https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git"
HUNYUAN_COMMIT = "82920d643c0dc2f7bfd7255f45f62d386edfe60c"
REALESRGAN_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
REALESRGAN_SHA256 = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"

# The upstream all-in-one requirements file pins NumPy 1.24.4.  That release
# has no Python 3.12 wheel, so pip attempts a source build in current hosted
# environments and fails before model setup.  This is the runtime subset used
# by the Shape/Paint pipeline, not its optional Blender, web-demo, Open3D,
# MeshLab, or distributed-training extras.  NumPy <2 preserves the API the
# pinned 2025 Hunyuan source expects while supporting Python 3.10--3.12.
HUNYUAN_RUNTIME_REQUIREMENTS = """\
ninja==1.11.1.1
pybind11==2.13.4
transformers==4.46.0
diffusers==0.30.0
accelerate==1.1.1
pytorch-lightning==1.9.5
huggingface-hub==0.30.2
safetensors==0.4.4
numpy>=1.26,<2
scipy==1.14.1
einops==0.8.0
pandas==2.2.2
opencv-python==4.10.0.84
imageio==2.36.0
scikit-image==0.24.0
rembg==2.0.65
realesrgan==0.3.0
basicsr==1.4.2
trimesh==4.4.7
# Hunyuan Shape imports pymeshlab at module import time.  Its upstream
# 2022 pin stops at Python 3.11, so use the closest release with CPython 3.12
# Linux wheels for the hosted runtime.
pymeshlab==2023.12.post1
pygltflib==1.16.3
xatlas==0.0.9
omegaconf==2.3.0
pyyaml==6.0.2
configargparse==1.7
cupy-cuda12x==13.4.1
# 1.16.3 publishes no Python 3.12 wheel.  The compatible range retains the
# CPU inference API used by rembg while allowing the hosted Python 3.12 image.
onnxruntime>=1.17,<1.22
torchmetrics==1.6.0
pydantic==2.10.6
timm
torchdiffeq
"""


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def clone_at(repository: str, commit: str, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"refusing to alter existing third-party checkout: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", repository, str(destination)])
    run(["git", "checkout", "--detach", commit], destination)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=destination, text=True).strip()
    if actual != commit:
        raise RuntimeError(f"pinned checkout mismatch: expected {commit}, got {actual}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_realesrgan(destination: Path) -> None:
    if destination.is_file():
        actual = sha256(destination)
        if actual == REALESRGAN_SHA256:
            return
        raise RuntimeError(f"unexpected RealESRGAN checkpoint hash: {actual}; remove {destination} before retrying")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    try:
        print(f"+ downloading {REALESRGAN_URL}", flush=True)
        urllib.request.urlretrieve(REALESRGAN_URL, temporary)
        actual = sha256(temporary)
        if actual != REALESRGAN_SHA256:
            raise RuntimeError(f"RealESRGAN checkpoint hash mismatch: expected {REALESRGAN_SHA256}, got {actual}")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("third_party"))
    parser.add_argument("--sam2", action="store_true", help="install the pinned SAM2 automatic-segmentation source")
    parser.add_argument("--hunyuan", action="store_true", help="install the pinned Hunyuan3D-2.1 source")
    parser.add_argument(
        "--skip-hunyuan-paint",
        action="store_true",
        help="install Shape only; do not compile the CUDA-only Hunyuan Paint rasterizer",
    )
    parser.add_argument("--accept-hunyuan-license", action="store_true", help="required acknowledgement before Hunyuan source is fetched")
    args = parser.parse_args()
    if not args.sam2 and not args.hunyuan:
        parser.error("select at least one model: --sam2 and/or --hunyuan")
    if args.hunyuan and not args.accept_hunyuan_license:
        parser.error("Hunyuan3D-2.1 has its own licence; inspect it and pass --accept-hunyuan-license only if it permits your use.")
    if args.sam2:
        sam2 = args.root / "sam2"
        clone_at(SAM2_REPOSITORY, SAM2_COMMIT, sam2)
        run([sys.executable, "-m", "pip", "install", "-e", "."], sam2)
    if args.hunyuan:
        hunyuan = args.root / "Hunyuan3D-2.1"
        clone_at(HUNYUAN_REPOSITORY, HUNYUAN_COMMIT, hunyuan)
        compatible_requirements = hunyuan / "asset_baseline_runtime_requirements.txt"
        compatible_requirements.write_text(HUNYUAN_RUNTIME_REQUIREMENTS, encoding="utf-8")
        run([sys.executable, "-m", "pip", "install", "-r", str(compatible_requirements)], hunyuan)
        if args.skip_hunyuan_paint:
            print("+ Hunyuan Paint build skipped: Shape-only profile requested", flush=True)
        else:
            run([sys.executable, "-m", "pip", "install", "-e", "hy3dpaint/custom_rasterizer"], hunyuan)
            run(["bash", "compile_mesh_painter.sh"], hunyuan / "hy3dpaint" / "DifferentiableRenderer")
            download_realesrgan(hunyuan / "hy3dpaint" / "ckpt" / "RealESRGAN_x4plus.pth")


if __name__ == "__main__":
    main()
