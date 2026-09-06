"""pack46: pack28 + item_022 silver hang flap and two punch holes."""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(r"C:\Users\MACAU\Desktop\天池")
DESK = Path(r"C:\Users\MACAU\Desktop")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PACK28 = DESK / "pack28.zip"
SUB = ROOT / "output" / "submission"
USD_ROOT = SUB / "submission"
sys.path.insert(0, str(ROOT / "work" / "preview_pack34"))
from add_part_usd import add_box, add_cylinder  # noqa: E402

SILVER = (0.82, 0.83, 0.85)
HOLE = (0.62, 0.63, 0.65)


def extract_pack28() -> None:
    if SUB.exists():
        shutil.rmtree(SUB)
    SUB.mkdir(parents=True)
    with zipfile.ZipFile(PACK28) as archive:
        archive.extractall(SUB)
    print("extracted pack28", len(list(USD_ROOT.glob("item_*"))))


def crc_map(path: Path) -> dict[str, tuple[int, int]]:
    with zipfile.ZipFile(path) as archive:
        return {info.filename: (info.file_size, info.CRC) for info in archive.infolist() if not info.is_dir()}


def write_zip(dest: Path) -> None:
    if dest.exists():
        dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted((SUB / "submission").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(SUB).as_posix())


def render(item_id: str, stem: str) -> None:
    command = [
        str(BLENDER),
        "--background",
        "--python",
        str(ROOT / "work" / "preview_pack34" / "qa_item.py"),
        "--",
        item_id,
        stem,
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(item_id, "render", result.returncode)
    print((result.stdout or "")[-800:])
    if result.returncode != 0:
        raise SystemExit(f"render failed {item_id}")


def main() -> None:
    extract_pack28()
    usd = USD_ROOT / "item_022" / "item_022.usd"
    render("item_022", "item_022_pack28")
    add_box(
        str(usd),
        "/item_022/Asset/hang_flange",
        (-0.192, 0.0, 0.198),
        (0.024, 0.074, 0.072),
        SILVER,
    )
    add_cylinder(
        str(usd),
        "/item_022/Asset/hang_hole_a",
        (-0.192, -0.016, 0.210),
        0.009,
        0.028,
        HOLE,
        (0.0, 90.0, 0.0),
    )
    add_cylinder(
        str(usd),
        "/item_022/Asset/hang_hole_b",
        (-0.192, 0.016, 0.210),
        0.009,
        0.028,
        HOLE,
        (0.0, 90.0, 0.0),
    )
    render("item_022", "item_022_pack46")
    out = DESK / "pack46.zip"
    write_zip(out)
    shutil.copy2(out, ROOT / "output" / "submission_pack46_paper_hang.zip")
    before, after = crc_map(PACK28), crc_map(out)
    diffs = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
    print("size", out.stat().st_size, "diffs", diffs)
    if diffs != ["submission/item_022/item_022.usd"]:
        raise SystemExit(f"CRC mismatch: {diffs}")
    print("CRC_OK")


if __name__ == "__main__":
    main()
