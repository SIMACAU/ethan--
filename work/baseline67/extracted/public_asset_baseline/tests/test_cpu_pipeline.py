from __future__ import annotations

import zipfile
from pathlib import Path

import cv2
import numpy as np

from asset_baseline.input_data import inspect_inputs
from asset_baseline.pipeline import run_all


def _write_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 48))
    assert writer.isOpened()
    for index in range(4):
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        cv2.rectangle(frame, (12 + index, 10), (48 + index, 38), (20, 160, 230), -1)
        writer.write(frame)
    writer.release()


def _official_like_inputs(root: Path) -> tuple[Path, Path]:
    source = root / "source"
    for index in range(1, 35):
        _write_video(source / f"item_{index:03d}" / "turntable.mp4")
    question = root / "question.zip"
    with zipfile.ZipFile(question, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for video in sorted(source.rglob("*.mp4")):
            archive.write(video, video.relative_to(source).as_posix())
    example = root / "submission_example.zip"
    with zipfile.ZipFile(example, "w") as archive:
        archive.writestr("submission_example/submission/item_001/item_001.usd", "# placeholder")
    return question, example


def test_inspect_accepts_the_expected_input_contract(tmp_path: Path) -> None:
    question, example = _official_like_inputs(tmp_path)
    manifest = inspect_inputs(question, example)
    assert manifest["task_count"] == 34
    assert manifest["video_count"] == 34


def test_cpu_smoke_pipeline_generates_a_valid_submission(tmp_path: Path) -> None:
    question, example = _official_like_inputs(tmp_path)
    config = {
        "run_name": "cpu_smoke",
        "seed": 7,
        "question_zip": str(question),
        "submission_example_zip": str(example),
        "output_root": str(tmp_path / "outputs"),
        "video": {"frames_per_video": 2, "selected_views": 1, "max_edge": 128, "jpeg_quality": 90},
        "reconstruction": {"backend": "primitive", "hunyuan_repo": "unused", "hunyuan_model": "unused", "hunyuan_texture": False, "max_faces": 30000},
        "segmentation": {"backend": "center", "sam2_repo": "unused", "sam2_model": "unused", "min_area_fraction": 0.03, "max_area_fraction": 0.90},
        "physics": {"collision_mode": "convex_hull", "default_mass_kg": 1.0, "density_kg_m3": 700.0, "friction": 0.8, "simulation_steps": 4},
        "package": {"archive_root": "submission_example/submission", "compression_level": 6},
    }
    report = run_all(config)
    assert report["valid"] is True
    assert report["valid_tasks"] == 34
    package = tmp_path / "outputs/cpu_smoke/packages/asset_baseline_submission.zip"
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        assert sum(name.endswith(".usd") for name in archive.namelist()) == 34
