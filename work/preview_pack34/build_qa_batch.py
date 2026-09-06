"""Restore pack28, rebuild selected items without video wrap, restore textures, render QA."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(r"C:\Users\MACAU\Desktop\天池")
DESK = Path(r"C:\Users\MACAU\Desktop")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PACK28 = DESK / "pack28.zip"
SUB = ROOT / "output" / "submission"
USD_ROOT = SUB / "submission"
ITEMS = ["item_001", "item_003", "item_004", "item_008", "item_012", "item_017"]


def extract_pack28() -> dict[str, bytes]:
    if SUB.exists():
        shutil.rmtree(SUB)
    SUB.mkdir(parents=True)
    textures: dict[str, bytes] = {}
    with zipfile.ZipFile(PACK28) as archive:
        archive.extractall(SUB)
        for info in archive.infolist():
            if info.is_dir():
                continue
            lower = info.filename.lower()
            if lower.endswith((".jpg", ".jpeg", ".png")):
                textures[info.filename] = archive.read(info)
    print("extracted pack28", len(list(USD_ROOT.glob("item_*"))))
    return textures


def restore_textures(textures: dict[str, bytes]) -> None:
    for name, data in textures.items():
        dest = SUB / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


def build_item(item_id: str) -> None:
    usd = USD_ROOT / item_id / f"{item_id}.usd"
    if usd.parent.exists():
        shutil.rmtree(usd.parent)
    usd.parent.mkdir(parents=True)
    log_path = ROOT / "work" / "packaging_logs" / f"{item_id}_qa.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(BLENDER),
        "--background",
        "--python",
        str(ROOT / "scripts" / "blender_build_item.py"),
        "--",
        item_id,
        str(usd),
    ]
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not usd.exists():
        raise SystemExit(f"build failed {item_id} see {log_path}")
    print(item_id, "usd", usd.stat().st_size)


def render_item(item_id: str) -> None:
    command = [
        str(BLENDER),
        "--background",
        "--python",
        str(ROOT / "work" / "preview_pack34" / "qa_item.py"),
        "--",
        item_id,
        f"{item_id}_qa",
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(item_id, "render", result.returncode)
    tail = (result.stdout or "") + "\n" + (result.stderr or "")
    print(tail[-800:])
    if result.returncode != 0:
        raise SystemExit(f"render failed {item_id}")


def main() -> None:
    textures = extract_pack28()
    for item_id in ITEMS:
        build_item(item_id)
    restore_textures(textures)
    for item_id in ITEMS:
        render_item(item_id)
    print("done")


if __name__ == "__main__":
    main()
