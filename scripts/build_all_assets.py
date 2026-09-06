"""Build every competition USD and pack submission.zip."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from asset_catalog import CATALOG, all_item_ids

BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")


# Only fully printed packages benefit from the cropped-foreground albedo; every
# other item keeps the raw first video frame that the 47.05 pack used.
ALBEDO_KINDS = {
    "juice_box",
    "tissue_box",
    "toilet_paper",
    "chip_bag",
    "chip_can",
    "seasoning_box",
}


def choose_texture(root: Path, item_id: str, spec: dict, use_albedo: bool) -> Path | None:
    item_dir = root / "work" / "photogrammetry" / item_id
    if use_albedo and spec["kind"] in ALBEDO_KINDS:
        albedo = item_dir / "albedo.jpg"
        if albedo.exists() and albedo.stat().st_size > 8000:
            return albedo
    frames = sorted((item_dir / "images").glob("*.jpg"))
    return frames[0] if frames else None


def atlas_is_usable(atlas: Path) -> bool:
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return True
    with Image.open(atlas) as image:
        image = image.convert("RGB")
        image.thumbnail((128, 128))
        arr = np.asarray(image).astype("float32")
    fill = np.array([255.0, 140.0, 0.0])
    dist = np.linalg.norm(arr - fill, axis=2)
    fill_ratio = float((dist < 40.0).mean())
    return fill_ratio < 0.50


def photogrammetry_glb(root: Path, item_id: str) -> Path | None:
    recon = root / "work" / "photogrammetry" / item_id / "reconstruction.json"
    if not recon.exists():
        return None
    payload = json.loads(recon.read_text(encoding="utf-8"))
    glb = payload.get("textured_glb")
    if not glb:
        return None
    path = Path(glb)
    if not path.exists() or path.stat().st_size < 2_000_000:
        return None
    atlas = path.parent / "scene_textured_material_00_map_Kd.jpg"
    if atlas.exists() and not atlas_is_usable(atlas):
        return None
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--items", nargs="*", default=[])
    parser.add_argument("--submission-name", default="submission.zip")
    parser.add_argument("--no-photogrammetry", action="store_true")
    parser.add_argument("--no-albedo", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    items = args.items or all_item_ids()
    if not BLENDER.exists():
        raise FileNotFoundError(BLENDER)

    package_root = root / "output" / "submission" / "submission"
    logs = root / "work" / "packaging_logs"
    package_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    built: list[dict] = []
    failures: list[str] = []
    for item_id in items:
        spec = CATALOG[item_id]
        output_usd = package_root / item_id / f"{item_id}.usd"
        if output_usd.parent.exists():
            shutil.rmtree(output_usd.parent, ignore_errors=True)
        output_usd.parent.mkdir(parents=True, exist_ok=True)
        texture = choose_texture(root, item_id, spec, use_albedo=not args.no_albedo)
        glb = None if args.no_photogrammetry else photogrammetry_glb(root, item_id)
        command = [
            str(BLENDER),
            "--background",
            "--python",
            str(root / "scripts" / "blender_build_item.py"),
            "--",
            item_id,
            str(output_usd),
        ]
        if texture:
            command.extend(["--texture", str(texture)])
        if glb:
            command.extend(["--glb", str(glb)])
        log_path = logs / f"{item_id}.log"
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            result = subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        if result.returncode != 0 or not output_usd.exists() or output_usd.stat().st_size == 0:
            failures.append(item_id)
            print(f"{item_id}: FAILED ({log_path})")
            continue
        built.append(
            {
                "item_id": item_id,
                "label": spec["label"],
                "usd": output_usd.relative_to(root / "output" / "submission").as_posix(),
                "bytes": output_usd.stat().st_size,
                "used_photogrammetry": bool(glb),
            }
        )
        print(f"{item_id}: {output_usd} ({output_usd.stat().st_size} bytes)")

    archive_path = root / "output" / args.submission_name
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(package_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root / "output" / "submission").as_posix())

    report = {
        "archive": str(archive_path),
        "archive_bytes": archive_path.stat().st_size if archive_path.exists() else 0,
        "built": built,
        "failures": failures,
    }
    (root / "reports" / "submission_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"built": len(built), "failures": failures, "archive_bytes": report["archive_bytes"]}, ensure_ascii=False))
    if failures:
        raise SystemExit("USD build failed for: " + ", ".join(failures))
    if report["archive_bytes"] > 2 * 1024**3:
        raise SystemExit("Archive exceeds 2 GiB")


if __name__ == "__main__":
    main()
