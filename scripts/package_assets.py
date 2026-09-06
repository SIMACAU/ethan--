"""Convert reconstructed GLBs into competition USDs and build submission.zip."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import zipfile
from pathlib import Path


BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")


def physical_profile(label: str) -> tuple[float, float, bool]:
    """Return target maximum dimension (m), mass (kg), and static flag."""
    rules = [
        (r"环境|办公室|茶水间", 8.0, 0.0, True),
        (r"沙发", 2.2, 55.0, True),
        (r"落地灯", 1.7, 5.0, True),
        (r"柜|边柜", 1.4, 35.0, True),
        (r"转椅|单人椅", 1.1, 12.0, False),
        (r"脚凳", 0.45, 4.0, False),
        (r"桌", 0.75, 12.0, True),
        (r"显示器", 0.55, 4.5, True),
        (r"笔记本电脑", 0.36, 2.0, False),
        (r"微波炉|空气炸锅|电饭煲|面包机", 0.50, 7.0, False),
        (r"电热水壶", 0.30, 1.2, False),
        (r"垃圾桶", 0.45, 1.0, False),
        (r"水果刀", 0.30, 0.15, False),
        (r"鼠标", 0.12, 0.10, False),
        (r"抽纸", 0.23, 0.45, False),
        (r"卷纸", 0.12, 0.18, False),
        (r"马克杯", 0.14, 0.35, False),
        (r"薯片袋|调味料", 0.28, 0.25, False),
        (r"罐装薯片", 0.30, 0.20, False),
        (r"锅铲", 0.36, 0.12, False),
        (r"木碗", 0.18, 0.20, False),
        (r"盘子|砧板", 0.35, 0.45, False),
        (r"炒锅", 0.55, 1.5, False),
        (r"果汁箱", 0.40, 3.0, False),
    ]
    for pattern, dimension, mass, is_static in rules:
        if re.search(pattern, label):
            return dimension, mass, is_static
    return 0.50, 1.0, False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--items", nargs="+", required=True)
    parser.add_argument("--max-faces", type=int, default=200_000)
    parser.add_argument("--submission-name", default="submission.zip")
    args = parser.parse_args()

    root = args.root.resolve()
    if not BLENDER.exists():
        raise FileNotFoundError(f"Blender executable not found: {BLENDER}")
    manifest = json.loads(
        (root / "reports" / "dataset_manifest.json").read_text(encoding="utf-8")
    )
    labels = {
        video["item_id"]: video["object_label"] for video in manifest["videos"]
    }

    submission_root = root / "output" / "submission"
    package_root = submission_root / "submission"
    logs = root / "work" / "packaging_logs"
    package_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    packaged: list[dict] = []

    for item_id in args.items:
        reconstruction_path = (
            root / "work" / "photogrammetry" / item_id / "reconstruction.json"
        )
        reconstruction = json.loads(reconstruction_path.read_text(encoding="utf-8"))
        input_glb_value = reconstruction.get("textured_glb")
        if not input_glb_value:
            raise RuntimeError(f"No textured GLB recorded for {item_id}")
        input_glb = Path(input_glb_value)
        if not input_glb.exists():
            raise FileNotFoundError(input_glb)

        label = labels[item_id]
        dimension, mass, is_static = physical_profile(label)
        item_output = package_root / item_id
        item_output.mkdir(parents=True, exist_ok=True)
        output_usd = item_output / f"{item_id}.usd"
        command = [
            str(BLENDER),
            "--background",
            "--python",
            str(root / "scripts" / "blender_package_usd.py"),
            "--",
            str(input_glb),
            str(output_usd),
            item_id,
            label,
            "--target-max-dimension",
            str(dimension),
            "--mass-kg",
            str(mass),
            "--max-faces",
            str(args.max_faces),
        ]
        if is_static:
            command.append("--static")
        with (logs / f"{item_id}.log").open(
            "w", encoding="utf-8", errors="replace"
        ) as log:
            result = subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        if result.returncode != 0 or not output_usd.exists():
            raise RuntimeError(
                f"Blender USD packaging failed for {item_id}; "
                f"see {logs / f'{item_id}.log'}"
            )
        packaged.append(
            {
                "item_id": item_id,
                "label": label,
                "usd": output_usd.relative_to(submission_root).as_posix(),
                "target_max_dimension_m": dimension,
                "mass_kg": mass,
                "static": is_static,
            }
        )
        print(f"{item_id}: {output_usd}")

    archive_path = root / "output" / args.submission_name
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for path in sorted(package_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(submission_root).as_posix())

    archive_bytes = archive_path.stat().st_size
    if archive_bytes > 2 * 1024**3:
        raise RuntimeError(f"Submission archive exceeds 2 GiB: {archive_bytes}")
    report = {
        "archive": str(archive_path),
        "archive_bytes": archive_bytes,
        "packaged": packaged,
    }
    (root / "reports" / "submission_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
