"""Build pack42/43/44 from pack28 by adding one visible part each."""

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
from add_part_usd import add_box  # noqa: E402


PACKS = [
    {
        "name": "pack42",
        "item": "item_016",
        "xform": "/item_016/Asset/basket/handle/handle_btn",
        "translate": (0.0, 0.0, 0.062),
        "size": (0.030, 0.020, 0.012),
        "zip_name": "pack42.zip",
        "stem": "item_016_pack42",
    },
    {
        "name": "pack43",
        "item": "item_015",
        "xform": "/item_015/Asset/lid/lid_handle",
        "translate": (0.0, -0.118, 0.040),
        "size": (0.080, 0.018, 0.012),
        "zip_name": "pack43.zip",
        "stem": "item_015_pack43",
    },
    {
        "name": "pack44",
        "item": "item_020",
        "xform": "/item_020/Asset/Body/logo",
        "translate": (0.0, 0.028, 0.080),
        "size": (0.090, 0.004, 0.022),
        "zip_name": "pack44.zip",
        "stem": "item_020_pack44",
    },
]


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
    print((result.stdout or "")[-600:])
    if result.returncode != 0:
        raise SystemExit(f"render failed {item_id}")


def main() -> None:
    if not PACK28.exists():
        raise SystemExit("missing pack28")
    for spec in PACKS:
        extract_pack28()
        usd = USD_ROOT / spec["item"] / f"{spec['item']}.usd"
        add_box(str(usd), spec["xform"], spec["translate"], spec["size"])
        render(spec["item"], spec["stem"])
        out = DESK / spec["zip_name"]
        write_zip(out)
        shutil.copy2(out, ROOT / "output" / f"submission_{spec['name']}.zip")
        before, after = crc_map(PACK28), crc_map(out)
        diffs = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
        expected = f"submission/{spec['item']}/{spec['item']}.usd"
        print(spec["name"], "size", out.stat().st_size, "diffs", diffs)
        if diffs != [expected]:
            raise SystemExit(f"CRC mismatch {spec['name']}: {diffs}")
        print(spec["name"], "CRC_OK")
    extract_pack28()
    print("restored pack28 workspace")


if __name__ == "__main__":
    main()
