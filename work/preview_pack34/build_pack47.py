"""pack47: pack28 + item_025 albedo cropped to bag only, orange fill, no geo change."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(r"C:\Users\MACAU\Desktop\天池")
DESK = Path(r"C:\Users\MACAU\Desktop")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PACK28 = DESK / "pack28.zip"
SUB = ROOT / "output" / "submission"
USD_ROOT = SUB / "submission"
PG = ROOT / "work" / "photogrammetry" / "item_025"


def extract_pack28() -> None:
    if SUB.exists():
        shutil.rmtree(SUB)
    SUB.mkdir(parents=True)
    with zipfile.ZipFile(PACK28) as archive:
        archive.extractall(SUB)


def crc_map(path: Path) -> dict[str, tuple[int, int]]:
    with zipfile.ZipFile(path) as archive:
        return {info.filename: (info.file_size, info.CRC) for info in archive.infolist() if not info.is_dir()}


def write_zip(dest: Path) -> None:
    if dest.exists():
        dest.unlink()
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted((SUB / "submission").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(SUB).as_posix())


def clean_albedo() -> Path:
    image = Image.open(PG / "images" / "video_01_frame_0001.jpg").convert("RGB")
    mask = Image.open(PG / "masks" / "video_01_frame_0001.jpg.png").convert("L")
    if mask.size != image.size:
        mask = mask.resize(image.size, Image.Resampling.NEAREST)
    arr = np.asarray(mask)
    ys, xs = np.where(arr > 40)
    if xs.size == 0:
        raise RuntimeError("empty mask")
    pad = 6
    left, right = max(int(xs.min()) - pad, 0), min(int(xs.max()) + pad, image.width - 1)
    top, bottom = max(int(ys.min()) - pad, 0), min(int(ys.max()) + pad, image.height - 1)
    crop = image.crop((left, top, right + 1, bottom + 1))
    crop_mask = mask.crop((left, top, right + 1, bottom + 1))
    m = np.asarray(crop_mask) > 40
    # ignore the lowest 12% (turntable) when sampling fill color
    h = m.shape[0]
    usable = m.copy()
    usable[int(h * 0.88) :, :] = False
    pixels = np.asarray(crop)
    if usable.any():
        fill = tuple(int(v) for v in pixels[usable].mean(axis=0))
    else:
        fill = (240, 120, 40)
    # drop likely turntable: dark pixels in the bottom band even if masked
    bottom_band = slice(int(h * 0.82), h)
    dark = pixels[bottom_band].mean(axis=2) < 45
    m[bottom_band] = m[bottom_band] & ~dark
    ys2, xs2 = np.where(m)
    if xs2.size:
        left2, right2 = int(xs2.min()), int(xs2.max())
        top2, bottom2 = int(ys2.min()), int(ys2.max())
        pad2 = 4
        left2 = max(left2 - pad2, 0)
        top2 = max(top2 - pad2, 0)
        right2 = min(right2 + pad2, crop.width - 1)
        bottom2 = min(bottom2 + pad2, crop.height - 1)
        crop = crop.crop((left2, top2, right2 + 1, bottom2 + 1))
        m = m[top2 : bottom2 + 1, left2 : right2 + 1]
    out = Image.new("RGB", crop.size, fill)
    out.paste(crop, mask=Image.fromarray((m * 255).astype(np.uint8)))
    dest = ROOT / "work" / "preview_pack34" / "item_025_albedo_clean.jpg"
    out.save(dest, quality=92, optimize=True)
    print("albedo", dest, out.size, "fill", fill)
    return dest


def render(stem: str) -> None:
    command = [
        str(BLENDER),
        "--background",
        "--python",
        str(ROOT / "work" / "preview_pack34" / "qa_item.py"),
        "--",
        "item_025",
        stem,
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("render", result.returncode)
    print((result.stdout or "")[-500:])
    if result.returncode != 0:
        raise SystemExit("render failed")


def main() -> None:
    extract_pack28()
    render("item_025_pack28")
    cleaned = clean_albedo()
    target = USD_ROOT / "item_025" / "textures" / "albedo.jpg"
    shutil.copy2(cleaned, target)
    render("item_025_pack47")
    out = DESK / "pack47.zip"
    write_zip(out)
    shutil.copy2(out, ROOT / "output" / "submission_pack47_chipbag_albedo.zip")
    before, after = crc_map(PACK28), crc_map(out)
    diffs = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
    print("size", out.stat().st_size, "diffs", diffs)
    if diffs != ["submission/item_025/textures/albedo.jpg"]:
        raise SystemExit(f"CRC mismatch: {diffs}")
    print("CRC_OK")


if __name__ == "__main__":
    main()
