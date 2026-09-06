"""Pick the largest-mask appearance frame and save a cropped albedo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image
import numpy as np


def crop_foreground(image: Image.Image, mask: Image.Image, pad_ratio: float = 0.08) -> Image.Image:
    mask_l = mask.convert("L")
    if mask_l.size != image.size:
        mask_l = mask_l.resize(image.size, Image.Resampling.NEAREST)
    arr = np.asarray(mask_l)
    ys, xs = np.where(arr > 24)
    if xs.size == 0:
        return image.convert("RGB")
    left, right = int(xs.min()), int(xs.max())
    top, bottom = int(ys.min()), int(ys.max())
    pad_x = max(int((right - left + 1) * pad_ratio), 8)
    pad_y = max(int((bottom - top + 1) * pad_ratio), 8)
    left = max(left - pad_x, 0)
    top = max(top - pad_y, 0)
    right = min(right + pad_x, image.width - 1)
    bottom = min(bottom + pad_y, image.height - 1)
    rgb = image.convert("RGB")
    cropped = rgb.crop((left, top, right + 1, bottom + 1))
    alpha = mask_l.crop((left, top, right + 1, bottom + 1))
    rgba = cropped.convert("RGBA")
    rgba.putalpha(alpha)
    background = Image.new("RGB", rgba.size, (210, 210, 212))
    background.paste(cropped, mask=alpha)
    return background


def process_item(item_dir: Path) -> dict[str, int | str]:
    image_dir = item_dir / "images"
    mask_dir = item_dir / "masks"
    image_paths = sorted(image_dir.glob("*.jpg"))
    best_path = None
    best_area = -1
    for image_path in image_paths:
        mask_path = mask_dir / f"{image_path.name}.png"
        if not mask_path.exists():
            continue
        with Image.open(mask_path) as mask:
            area = int(np.count_nonzero(np.asarray(mask.convert("L")) > 24))
        if area > best_area:
            best_area = area
            best_path = image_path
    if best_path is None:
        return {"status": "skip", "reason": "no_masks"}
    with Image.open(best_path) as image, Image.open(mask_dir / f"{best_path.name}.png") as mask:
        albedo = crop_foreground(image, mask)
    out = item_dir / "albedo.jpg"
    albedo.save(out, quality=92, optimize=True)
    return {
        "status": "ok",
        "source": best_path.name,
        "area": best_area,
        "size": f"{albedo.width}x{albedo.height}",
        "bytes": out.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--items", nargs="*", default=[])
    args = parser.parse_args()
    root = args.root.resolve() / "work" / "photogrammetry"
    selected = set(args.items)
    summary = {}
    for item_dir in sorted(root.glob("item_*")):
        if selected and item_dir.name not in selected:
            continue
        if not item_dir.is_dir():
            continue
        summary[item_dir.name] = process_item(item_dir)
        print(f"{item_dir.name}: {summary[item_dir.name]}")
    (root / "albedo_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
