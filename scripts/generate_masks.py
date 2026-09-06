"""Generate automatic salient-object masks for COLMAP feature extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageFilter
from rembg import new_session, remove


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--items", nargs="*", default=[])
    parser.add_argument("--model", default="u2netp")
    parser.add_argument("--foregrounds", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    photogrammetry_root = root / "work" / "photogrammetry"
    selected = set(args.items)
    item_dirs = sorted(
        path
        for path in photogrammetry_root.glob("item_*")
        if path.is_dir() and (not selected or path.name in selected)
    )
    if selected - {path.name for path in item_dirs}:
        missing = ", ".join(sorted(selected - {path.name for path in item_dirs}))
        raise SystemExit(f"Prepared frames not found for: {missing}")

    session = new_session(args.model)
    summary: dict[str, dict[str, int | str]] = {}
    for item_dir in item_dirs:
        image_root = item_dir / "images"
        mask_root = item_dir / "masks"
        mvs_mask_root = item_dir / "mvs_masks"
        foreground_root = item_dir / "foregrounds"
        image_paths = sorted(path for path in image_root.glob("*.jpg") if path.is_file())
        completed = 0

        for image_path in image_paths:
            mask_path = mask_root / f"{image_path.name}.png"
            mvs_mask_path = mvs_mask_root / f"{image_path.name}.mask.png"
            foreground_path = foreground_root / image_path.with_suffix(".png").name
            if (
                not args.force
                and mask_path.exists()
                and mvs_mask_path.exists()
                and (not args.foregrounds or foreground_path.exists())
            ):
                completed += 1
                continue

            if not image_path.exists():
                continue
            mask_path.parent.mkdir(parents=True, exist_ok=True)
            mvs_mask_path.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(image_path) as source:
                source = source.convert("RGB")
                inference = source.copy()
                inference.thumbnail((640, 640))
                mask = remove(
                    inference,
                    session=session,
                    only_mask=True,
                    post_process_mask=True,
                ).convert("L")
                if mask.size != source.size:
                    mask = mask.resize(source.size, Image.Resampling.NEAREST)
                mask = mask.filter(ImageFilter.MaxFilter(5))
                mask.save(mask_path, optimize=True)
                mask.save(mvs_mask_path, optimize=True)

                if args.foregrounds:
                    foreground_path.parent.mkdir(parents=True, exist_ok=True)
                    rgba = source.convert("RGBA")
                    rgba.putalpha(mask)
                    rgba.save(foreground_path, optimize=True)
            completed += 1

        summary[item_dir.name] = {
            "model": args.model,
            "image_count": len(image_paths),
            "mask_count": completed,
        }
        print(f"{item_dir.name}: {completed}/{len(image_paths)} masks")

    (photogrammetry_root / "mask_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
