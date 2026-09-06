from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .util import utc_now


def _resize(frame: np.ndarray, max_edge: int) -> np.ndarray:
    height, width = frame.shape[:2]
    scale = min(1.0, max_edge / max(height, width))
    if scale >= 1.0:
        return frame
    return cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)


def _frame_score(frame: np.ndarray) -> dict[str, float]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast = float(gray.std())
    height, width = gray.shape
    central = gray[height // 4 : 3 * height // 4, width // 4 : 3 * width // 4]
    central_contrast = float(central.std())
    return {"sharpness": sharpness, "contrast": contrast, "central_contrast": central_contrast}


def _candidate_indices(frame_count: int, samples: int) -> list[int]:
    if frame_count <= 1:
        return [0]
    return sorted({round(index * (frame_count - 1) / max(samples - 1, 1)) for index in range(samples)})


def _colour_distance(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(left.astype(np.float64) - right.astype(np.float64)))


def _make_contact_sheet(records: list[dict[str, Any]], target: Path) -> None:
    thumbs: list[Image.Image] = []
    for record in records:
        image = Image.open(record["path"]).convert("RGB")
        image.thumbnail((240, 180))
        canvas = Image.new("RGB", (240, 204), "white")
        canvas.paste(image, ((240 - image.width) // 2, 0))
        ImageDraw.Draw(canvas).text((6, 184), f"{record['source_index']}:{record['frame_index']}", fill="black")
        thumbs.append(canvas)
    columns = 3
    rows = max(1, math.ceil(len(thumbs) / columns))
    sheet = Image.new("RGB", (columns * 240, rows * 204), "white")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % columns) * 240, (index // columns) * 204))
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target)


def extract_and_select_views(
    task_id: str,
    videos: list[dict[str, Any]],
    output_dir: Path,
    *,
    frames_per_video: int,
    selected_views: int,
    max_edge: int,
    jpeg_quality: int,
) -> dict[str, Any]:
    """Uniformly sample all clips then select sharp, visually diverse views."""
    candidates: list[dict[str, Any]] = []
    raw_dir = output_dir / "candidates"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source_index, video in enumerate(videos):
        capture = cv2.VideoCapture(str(video["path"]))
        if not capture.isOpened():
            raise RuntimeError(f"OpenCV could not decode video: {video['path']}")
        frame_count = max(1, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        for frame_index in _candidate_indices(frame_count, frames_per_video):
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            success, frame = capture.read()
            if not success or frame is None:
                continue
            frame = _resize(frame, max_edge)
            metrics = _frame_score(frame)
            colour = frame.reshape(-1, 3).mean(axis=0).tolist()
            path = raw_dir / f"s{source_index:02d}_f{frame_index:06d}.jpg"
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]):
                raise RuntimeError(f"failed to write frame: {path}")
            candidates.append({
                "path": str(path), "source_index": source_index, "source_video": video["member"],
                "frame_index": frame_index, "frame_count": frame_count, "fps": fps,
                "mean_bgr": colour, **metrics,
            })
        capture.release()
    if not candidates:
        raise RuntimeError(f"no decodable frames for {task_id}")
    for key in ("sharpness", "contrast", "central_contrast"):
        values = np.asarray([record[key] for record in candidates], dtype=np.float64)
        low, high = float(values.min()), float(values.max())
        for record in candidates:
            record[f"norm_{key}"] = (record[key] - low) / max(high - low, 1e-9)
    for record in candidates:
        record["base_score"] = sum(record[f"norm_{name}"] for name in ("sharpness", "contrast", "central_contrast"))
    ranked = sorted(candidates, key=lambda record: (-record["base_score"], record["source_index"], record["frame_index"]))
    chosen: list[dict[str, Any]] = []
    for candidate in ranked:
        diversity = 1.0 if not chosen else min(_colour_distance(np.asarray(candidate["mean_bgr"]), np.asarray(old["mean_bgr"])) / 255.0 for old in chosen)
        if len(chosen) < selected_views and (not chosen or diversity >= 0.04):
            candidate["diversity"] = diversity
            chosen.append(candidate)
    for candidate in ranked:
        if len(chosen) >= selected_views:
            break
        if candidate not in chosen:
            candidate["diversity"] = 0.0
            chosen.append(candidate)
    selected_dir = output_dir / "selected"
    selected_dir.mkdir(parents=True, exist_ok=True)
    selected: list[dict[str, Any]] = []
    for index, record in enumerate(chosen):
        target = selected_dir / f"view_{index:02d}.jpg"
        image = Image.open(record["path"]).convert("RGB")
        image.save(target, quality=jpeg_quality)
        selected.append({**record, "path": str(target), "view_index": index})
    _make_contact_sheet(selected, output_dir / "contact_sheet.jpg")
    return {"task_id": task_id, "created_at": utc_now(), "candidate_count": len(candidates), "selected": selected, "contact_sheet": str(output_dir / "contact_sheet.jpg")}
