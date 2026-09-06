from __future__ import annotations

import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .util import sha256, utc_now, write_json


TASK_PATTERN = re.compile(r"^item_(\d{3})$")
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".MP4", ".MOV", ".M4V", ".AVI"}


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    for info in archive.infolist():
        name = PurePosixPath(info.filename)
        if name.is_absolute() or ".." in name.parts:
            raise ValueError(f"unsafe ZIP member: {info.filename}")
        if not info.is_dir() and not info.filename.startswith("__MACOSX/"):
            members.append(info)
    if archive.testzip() is not None:
        raise ValueError(f"ZIP CRC failure: {archive.filename}")
    return members


def inspect_inputs(question_zip: Path, example_zip: Path) -> dict[str, Any]:
    if not question_zip.is_file():
        raise FileNotFoundError(question_zip)
    if not example_zip.is_file():
        raise FileNotFoundError(example_zip)
    with zipfile.ZipFile(question_zip) as archive:
        question_members = _safe_members(archive)
    with zipfile.ZipFile(example_zip) as archive:
        example_members = _safe_members(archive)

    tasks: dict[str, list[str]] = {}
    for info in question_members:
        path = PurePosixPath(info.filename)
        if len(path.parts) != 2 or path.suffix not in VIDEO_SUFFIXES:
            continue
        match = TASK_PATTERN.fullmatch(path.parts[0])
        if match is None:
            continue
        tasks.setdefault(path.parts[0], []).append(info.filename)
    expected = [f"item_{index:03d}" for index in range(1, 35)]
    missing = sorted(set(expected) - set(tasks))
    extras = sorted(set(tasks) - set(expected))
    if missing or extras:
        raise ValueError(f"question archive task inventory mismatch: missing={missing}, extras={extras}")
    example_prefix = "submission_example/submission/"
    if not any(info.filename.startswith(example_prefix) for info in example_members):
        raise ValueError("submission_example.zip lacks submission_example/submission/")
    return {
        "created_at": utc_now(),
        "input_contract": "official_question_zip_plus_official_submission_example_zip_only",
        "question_zip": {"path": str(question_zip), "sha256": sha256(question_zip), "bytes": question_zip.stat().st_size},
        "submission_example_zip": {"path": str(example_zip), "sha256": sha256(example_zip), "bytes": example_zip.stat().st_size},
        "task_count": len(tasks),
        "video_count": sum(len(value) for value in tasks.values()),
        "tasks": [{"task_id": task_id, "videos": sorted(tasks[task_id])} for task_id in expected],
        "example_member_count": len(example_members),
    }


def extract_question(question_zip: Path, manifest: dict[str, Any], output_root: Path) -> dict[str, Any]:
    """Extract only verified official videos under a new run directory."""
    output_root.mkdir(parents=True, exist_ok=True)
    wanted = {video for task in manifest["tasks"] for video in task["videos"]}
    records: list[dict[str, Any]] = []
    with zipfile.ZipFile(question_zip) as archive:
        infos = {info.filename: info for info in _safe_members(archive)}
        if wanted - set(infos):
            raise ValueError(f"question archive changed after inspection: {sorted(wanted - set(infos))[:3]}")
        for task in manifest["tasks"]:
            task_id = task["task_id"]
            for member in task["videos"]:
                target = output_root / member
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise FileExistsError(target)
                with archive.open(infos[member]) as source, target.open("xb") as destination:
                    while True:
                        block = source.read(1024 * 1024)
                        if not block:
                            break
                        destination.write(block)
                records.append({"task_id": task_id, "member": member, "path": str(target), "bytes": target.stat().st_size, "sha256": sha256(target)})
    return {"created_at": utc_now(), "video_root": str(output_root), "videos": records}


def write_input_manifest(question_zip: Path, example_zip: Path, destination: Path) -> dict[str, Any]:
    manifest = inspect_inputs(question_zip, example_zip)
    write_json(destination, manifest)
    return manifest
