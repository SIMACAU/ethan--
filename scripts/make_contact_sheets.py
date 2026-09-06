"""Extract evenly spaced video frames and create per-item contact sheets."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def extract_frames(
    video_path: Path,
    output_dir: Path,
    duration: float,
    sample_count: int,
    tile_width: int,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(output_dir.glob("frame_*.jpg"))
    if len(existing) == sample_count:
        return existing

    for path in existing:
        path.unlink()

    fps = sample_count / max(duration, 0.001)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps:.10f},scale={tile_width}:-2",
        "-frames:v",
        str(sample_count),
        "-q:v",
        "3",
        str(output_dir / "frame_%02d.jpg"),
    ]
    subprocess.run(command, check=True)
    return sorted(output_dir.glob("frame_*.jpg"))


def render_tile(
    frame_path: Path,
    label: str,
    width: int,
    image_height: int,
    header_height: int,
    font: ImageFont.ImageFont,
) -> Image.Image:
    with Image.open(frame_path) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        source.thumbnail((width, image_height), Image.Resampling.LANCZOS)
        tile = Image.new("RGB", (width, image_height + header_height), (20, 20, 20))
        x = (width - source.width) // 2
        y = header_height + (image_height - source.height) // 2
        tile.paste(source, (x, y))

    draw = ImageDraw.Draw(tile)
    draw.rectangle((0, 0, width, header_height), fill=(10, 10, 10))
    draw.text((8, 5), label, fill=(240, 240, 240), font=font)
    return tile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--samples", type=int, default=6)
    parser.add_argument("--tile-width", type=int, default=420)
    parser.add_argument("--tile-height", type=int, default=260)
    parser.add_argument("--clean-frames", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    manifest_path = root / "reports" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frame_root = root / "work" / "contact_sheet_frames"
    sheet_root = root / "reports" / "contact_sheets"
    sheet_root.mkdir(parents=True, exist_ok=True)

    by_item: dict[str, list[dict]] = {}
    for video in manifest["videos"]:
        by_item.setdefault(video["item_id"], []).append(video)

    header_height = 34
    font = load_font(18)
    completed = 0
    failures: list[str] = []

    for item_id, videos in sorted(by_item.items()):
        rows: list[list[Image.Image]] = []
        for video_index, video in enumerate(videos, start=1):
            duration = video.get("duration_seconds")
            if not duration:
                failures.append(f"{item_id}: missing duration for {video['path']}")
                continue
            source = root / video["path"]
            extraction_dir = frame_root / item_id / f"video_{video_index:02d}"
            try:
                frame_paths = extract_frames(
                    source,
                    extraction_dir,
                    float(duration),
                    args.samples,
                    args.tile_width,
                )
            except subprocess.CalledProcessError as exc:
                failures.append(f"{item_id}: ffmpeg failed for {video['path']}: {exc}")
                continue

            tiles = [
                render_tile(
                    frame_path,
                    f"{video['view']} {frame_number + 1}/{len(frame_paths)}",
                    args.tile_width,
                    args.tile_height,
                    header_height,
                    font,
                )
                for frame_number, frame_path in enumerate(frame_paths)
            ]
            if tiles:
                rows.append(tiles)

        if not rows:
            continue

        columns = max(len(row) for row in rows)
        sheet = Image.new(
            "RGB",
            (
                columns * args.tile_width,
                len(rows) * (args.tile_height + header_height),
            ),
            (0, 0, 0),
        )
        for row_index, row in enumerate(rows):
            for column_index, tile in enumerate(row):
                sheet.paste(
                    tile,
                    (
                        column_index * args.tile_width,
                        row_index * (args.tile_height + header_height),
                    ),
                )

        sheet_path = sheet_root / f"{item_id}.jpg"
        sheet.save(sheet_path, quality=90, optimize=True)
        completed += 1
        print(f"{item_id}: {sheet_path}")

    index = {
        "completed_items": completed,
        "expected_items": len(by_item),
        "samples_per_video": args.samples,
        "failures": failures,
    }
    (sheet_root / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if args.clean_frames:
        shutil.rmtree(frame_root, ignore_errors=True)

    print(json.dumps(index, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit("Some contact sheets could not be generated.")


if __name__ == "__main__":
    main()
