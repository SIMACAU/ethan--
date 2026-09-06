from __future__ import annotations

import platform
import sys
import zipfile
from pathlib import Path
from typing import Any

from .input_data import extract_question, inspect_inputs, write_input_manifest
from .media import extract_and_select_views
from .reconstruct import HunyuanReconstructor, _load_mesh, create_reconstructor, finalize_mesh, reconstruct_mesh
from .segmentation import make_conditioning_image
from .usd_asset import simulate_mjcf, write_usd_asset
from .util import clean_dir, iter_files, read_json, seed_everything, sha256, utc_now, write_json


def run_root(config: dict[str, Any]) -> Path:
    return Path(str(config["output_root"])) / str(config["run_name"])


def runtime_record(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_at": utc_now(),
        "input_contract": "question.zip + submission_example.zip only; no work/v* or historic submission input is permitted",
        "python": sys.version,
        "platform": platform.platform(),
        "config": config,
    }


def inspect(config: dict[str, Any]) -> dict[str, Any]:
    return inspect_inputs(Path(config["question_zip"]), Path(config["submission_example_zip"]))


def prepare(config: dict[str, Any]) -> Path:
    root = run_root(config)
    clean_dir(root)
    seed_everything(int(config["seed"]))
    manifest = write_input_manifest(Path(config["question_zip"]), Path(config["submission_example_zip"]), root / "manifests" / "inputs.json")
    write_json(root / "manifests" / "runtime.json", runtime_record(config))
    extracted = extract_question(Path(config["question_zip"]), manifest, root / "raw_videos")
    write_json(root / "manifests" / "extracted.json", extracted)
    by_task: dict[str, list[dict[str, Any]]] = {task["task_id"]: [] for task in manifest["tasks"]}
    for record in extracted["videos"]:
        by_task[record["task_id"]].append(record)
    view_records = []
    video_config = config["video"]
    for task in manifest["tasks"]:
        task_id = task["task_id"]
        view_records.append(extract_and_select_views(
            task_id,
            sorted(by_task[task_id], key=lambda record: record["member"]),
            root / "views" / task_id,
            frames_per_video=int(video_config["frames_per_video"]),
            selected_views=int(video_config["selected_views"]),
            max_edge=int(video_config["max_edge"]),
            jpeg_quality=int(video_config["jpeg_quality"]),
        ))
    write_json(root / "manifests" / "views.json", {"created_at": utc_now(), "tasks": view_records})
    return root


def _require_prepared(config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    root = run_root(config)
    manifest_path = root / "manifests" / "views.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"prepared views missing; run `asset_baseline prepare` first: {manifest_path}")
    return root, read_json(manifest_path)


def generate(config: dict[str, Any]) -> Path:
    root, views = _require_prepared(config)
    submission = root / "submission"
    if submission.exists():
        raise FileExistsError(f"generation already exists; use a new run_name: {submission}")
    seed_everything(int(config["seed"]))
    assets: list[dict[str, Any]] = []
    reconstructor = create_reconstructor(config["reconstruction"])
    if isinstance(reconstructor, HunyuanReconstructor) and reconstructor.sequential:
        staged: list[dict[str, Any]] = []
        # On a 24 GiB GPU, generate every Shape result first while Shape is
        # resident, then release it before Paint is loaded.
        for task in views["tasks"]:
            task_id = task["task_id"]
            selected = task["selected"]
            if not selected:
                raise RuntimeError(f"no selected views: {task_id}")
            task_root = root / "generated" / task_id
            conditioning_path = task_root / "conditioning.png"
            segmentation = make_conditioning_image(Path(selected[0]["path"]), conditioning_path, config["segmentation"])
            shape_path = reconstructor.generate_shape(conditioning_path, task_root / "mesh_shape.glb")
            staged.append({"task_id": task_id, "selected": selected[0], "task_root": task_root, "conditioning": conditioning_path, "segmentation": segmentation, "shape": shape_path})
        reconstructor.begin_texture_phase()
        for record in staged:
            final_path = reconstructor.generate_texture(
                record["shape"],
                record["conditioning"],
                record["task_root"] / "mesh_textured.obj",
            )
            mesh = finalize_mesh(
                record["task_id"],
                _load_mesh(final_path),
                record["task_root"] / "mesh.obj",
                config["reconstruction"],
                "Hunyuan3D-2.1",
            )
            asset = write_usd_asset(record["task_id"], Path(mesh["mesh"]), record["conditioning"], submission / record["task_id"], config["physics"])
            assets.append({"task_id": record["task_id"], "source_view": record["selected"], "segmentation": record["segmentation"], "mesh": mesh, "asset": asset})
        write_json(root / "manifests" / "assets.json", {"created_at": utc_now(), "tasks": assets})
        return root
    for task in views["tasks"]:
        task_id = task["task_id"]
        selected = task["selected"]
        if not selected:
            raise RuntimeError(f"no selected views: {task_id}")
        task_root = root / "generated" / task_id
        conditioning_path = task_root / "conditioning.png"
        segmentation = make_conditioning_image(Path(selected[0]["path"]), conditioning_path, config["segmentation"])
        mesh = reconstruct_mesh(
            task_id,
            conditioning_path,
            task_root / "mesh.obj",
            config["reconstruction"],
            reconstructor=reconstructor,
        )
        asset = write_usd_asset(task_id, Path(mesh["mesh"]), conditioning_path, submission / task_id, config["physics"])
        assets.append({"task_id": task_id, "source_view": selected[0], "segmentation": segmentation, "mesh": mesh, "asset": asset})
    write_json(root / "manifests" / "assets.json", {"created_at": utc_now(), "tasks": assets})
    return root


def _archive_members(submission: Path) -> list[Path]:
    expected = [submission / f"item_{index:03d}" / f"item_{index:03d}.usd" for index in range(1, 35)]
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        raise ValueError(f"submission has missing task USDs: {missing[:3]}")
    return list(iter_files(submission))


def package(config: dict[str, Any]) -> Path:
    root, _ = _require_prepared(config)
    submission = root / "submission"
    members = _archive_members(submission)
    package_path = root / "packages" / "asset_baseline_submission.zip"
    if package_path.exists():
        raise FileExistsError(package_path)
    package_path.parent.mkdir(parents=True)
    archive_root = str(config["package"]["archive_root"]).rstrip("/")
    level = int(config["package"]["compression_level"])
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=level, strict_timestamps=True) as archive:
        for source in members:
            relative = source.relative_to(submission).as_posix()
            info = zipfile.ZipInfo(f"{archive_root}/{relative}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=level)
    if zipfile.ZipFile(package_path).testzip() is not None:
        raise RuntimeError("generated ZIP CRC failure")
    write_json(root / "manifests" / "package.json", {"created_at": utc_now(), "package": str(package_path), "sha256": sha256(package_path), "bytes": package_path.stat().st_size, "file_count": len(members)})
    return package_path


def validate(config: dict[str, Any]) -> dict[str, Any]:
    root, _ = _require_prepared(config)
    submission = root / "submission"
    _archive_members(submission)
    from .validate import validate_submission_tree

    report = validate_submission_tree(submission, root / "physics", int(config["physics"]["simulation_steps"]))
    package_path = root / "packages" / "asset_baseline_submission.zip"
    if package_path.is_file():
        report["package"] = {"path": str(package_path), "sha256": sha256(package_path), "bytes": package_path.stat().st_size}
    write_json(root / "reports" / "validation.json", report)
    return report


def run_all(config: dict[str, Any]) -> dict[str, Any]:
    prepare(config)
    generate(config)
    package(config)
    return validate(config)
