"""Build a reproducible manifest for the Tianchi video dataset."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any


VIDEO_SUFFIXES = {".mov", ".mp4", ".mkv", ".avi", ".webm"}


def run_ffprobe(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return json.loads(result.stdout)


def parse_rate(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None


def parse_label_and_view(item_id: str, path: Path) -> tuple[str, str]:
    stem = path.stem
    prefix = f"{item_id}_"
    remainder = stem[len(prefix) :] if stem.startswith(prefix) else stem
    if "交互" in remainder:
        view = "interaction"
        label = remainder.split("交互", 1)[0]
    elif "外观" in remainder:
        view = "appearance"
        label = remainder.split("外观", 1)[0]
    else:
        view = "unknown"
        label = re.sub(r"[-_ ]?\d+$", "", remainder)
    return label.strip(" _-"), view


def inspect_video(item_id: str, path: Path, root: Path) -> dict[str, Any]:
    probe = run_ffprobe(path)
    video_stream = next(
        (stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"),
        {},
    )
    format_info = probe.get("format", {})
    label, view = parse_label_and_view(item_id, path)

    duration_raw = video_stream.get("duration") or format_info.get("duration")
    duration = float(duration_raw) if duration_raw not in {None, "N/A"} else None
    rotation = None
    for side_data in video_stream.get("side_data_list", []):
        if "rotation" in side_data:
            rotation = int(side_data["rotation"])
            break
    if rotation is None:
        rotate_tag = video_stream.get("tags", {}).get("rotate")
        rotation = int(rotate_tag) if rotate_tag is not None else 0

    return {
        "item_id": item_id,
        "object_label": label,
        "view": view,
        "path": path.relative_to(root).as_posix(),
        "filename": path.name,
        "bytes": path.stat().st_size,
        "codec": video_stream.get("codec_name"),
        "pixel_format": video_stream.get("pix_fmt"),
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "rotation_degrees": rotation,
        "fps": parse_rate(video_stream.get("avg_frame_rate")),
        "duration_seconds": duration,
        "frame_count": (
            int(video_stream["nb_frames"])
            if str(video_stream.get("nb_frames", "")).isdigit()
            else None
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Competition workspace containing item_* directories.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Manifest destination (defaults to ROOT/reports).",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = (args.output_dir or root / "reports").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    item_dirs = sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and re.fullmatch(r"item_\d{3}", path.name)
    )
    videos: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for item_dir in item_dirs:
        video_paths = sorted(
            path
            for path in item_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
        )
        for video_path in video_paths:
            try:
                videos.append(inspect_video(item_dir.name, video_path, root))
            except (OSError, subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
                errors.append(
                    {
                        "item_id": item_dir.name,
                        "path": video_path.relative_to(root).as_posix(),
                        "error": str(exc),
                    }
                )

    expected_items = {f"item_{index:03d}" for index in range(1, 35)}
    actual_items = {path.name for path in item_dirs}
    summary = {
        "item_count": len(item_dirs),
        "video_count": len(videos),
        "total_bytes": sum(video["bytes"] for video in videos),
        "missing_items": sorted(expected_items - actual_items),
        "unexpected_items": sorted(actual_items - expected_items),
        "probe_error_count": len(errors),
    }
    manifest = {"summary": summary, "videos": videos, "errors": errors}

    json_path = output_dir / "dataset_manifest.json"
    json_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    csv_path = output_dir / "dataset_manifest.csv"
    fieldnames = list(videos[0]) if videos else []
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(videos)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")

    if errors:
        raise SystemExit("One or more videos could not be probed.")


if __name__ == "__main__":
    main()
