"""Extract appearance-video frames for automatic photogrammetry."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def allocate_frames(videos: list[dict], maximum: int, minimum_per_video: int) -> list[int]:
    durations = [max(float(video.get("duration_seconds") or 0), 0.001) for video in videos]
    total_duration = sum(durations)
    counts = [
        max(minimum_per_video, int(round(maximum * duration / total_duration)))
        for duration in durations
    ]
    while sum(counts) > maximum and any(count > minimum_per_video for count in counts):
        index = max(range(len(counts)), key=counts.__getitem__)
        counts[index] -= 1
    return counts


def extract_video_frames(
    source: Path,
    destination: Path,
    duration: float,
    frame_count: int,
    max_width: int,
    prefix: str,
) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    existing = sorted(destination.glob(f"{prefix}_frame_*.jpg"))
    if len(existing) == frame_count:
        return existing
    for path in existing:
        path.unlink()

    sampling_fps = frame_count / max(duration, 0.001)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vf",
        f"fps={sampling_fps:.12f},scale=w='min({max_width},iw)':h=-2:flags=lanczos",
        "-frames:v",
        str(frame_count),
        "-q:v",
        "2",
        str(destination / f"{prefix}_frame_%04d.jpg"),
    ]
    subprocess.run(command, check=True)
    return sorted(destination.glob(f"{prefix}_frame_*.jpg"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--items",
        nargs="*",
        default=[],
        help="Optional item IDs; defaults to every item.",
    )
    parser.add_argument("--max-frames", type=int, default=100)
    parser.add_argument("--min-frames-per-video", type=int, default=12)
    parser.add_argument("--max-width", type=int, default=1600)
    args = parser.parse_args()

    root = args.root.resolve()
    manifest = json.loads(
        (root / "reports" / "dataset_manifest.json").read_text(encoding="utf-8")
    )
    selected = set(args.items)
    by_item: dict[str, list[dict]] = {}
    for video in manifest["videos"]:
        if video["view"] != "appearance":
            continue
        if selected and video["item_id"] not in selected:
            continue
        by_item.setdefault(video["item_id"], []).append(video)

    if selected - set(by_item):
        missing = ", ".join(sorted(selected - set(by_item)))
        raise SystemExit(f"No appearance videos found for: {missing}")

    output_root = root / "work" / "photogrammetry"
    summary: dict[str, dict] = {}
    for item_id, videos in sorted(by_item.items()):
        videos.sort(key=lambda video: video["path"])
        counts = allocate_frames(
            videos,
            maximum=args.max_frames,
            minimum_per_video=args.min_frames_per_video,
        )
        item_frames = output_root / item_id / "images"
        all_frames: list[dict] = []

        for video_index, (video, frame_count) in enumerate(zip(videos, counts), start=1):
            frames = extract_video_frames(
                root / video["path"],
                item_frames,
                float(video["duration_seconds"]),
                frame_count,
                args.max_width,
                f"video_{video_index:02d}",
            )
            all_frames.extend(
                {
                    "frame": frame.relative_to(item_frames).as_posix(),
                    "source_video": video["path"],
                    "source_view": video["view"],
                }
                for frame in frames
            )

        item_summary = {
            "item_id": item_id,
            "object_label": videos[0]["object_label"],
            "video_count": len(videos),
            "frame_count": len(all_frames),
            "max_width": args.max_width,
            "frames": all_frames,
        }
        (output_root / item_id / "frames_manifest.json").write_text(
            json.dumps(item_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary[item_id] = {
            key: value for key, value in item_summary.items() if key != "frames"
        }
        print(
            f"{item_id} ({item_summary['object_label']}): "
            f"{item_summary['frame_count']} frames"
        )

    (output_root / "frames_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
