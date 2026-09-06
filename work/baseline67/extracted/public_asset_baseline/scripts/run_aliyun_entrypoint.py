#!/usr/bin/env python3
"""Run the GPU pipeline in the released Linux container with a durable receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_manifest() -> list[dict[str, object]]:
    """Hash code/config only; models and competition inputs are excluded."""
    selected = (ROOT / "pyproject.toml", ROOT / "requirements-gpu.txt", ROOT / "config", ROOT / "src", ROOT / "scripts")
    files: list[Path] = []
    for item in selected:
        files.extend([item] if item.is_file() else sorted(path for path in item.rglob("*") if path.is_file()))
    return [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in files]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", type=Path, required=True)
    parser.add_argument("--submission-example", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-name", default="asset_baseline_gpu")
    parser.add_argument("--accept-hunyuan-license", action="store_true")
    args = parser.parse_args()
    if not args.accept_hunyuan_license:
        parser.error("read the Hunyuan3D-2.1 LICENSE before passing --accept-hunyuan-license")
    question, example = args.question.resolve(), args.submission_example.resolve()
    if not question.is_file() or not example.is_file():
        parser.error("both official ZIP inputs must exist")

    output_root = args.output_root.resolve()
    run_root = output_root / args.run_name
    process = run_root / "process"
    commands = process / "commands.jsonl"

    def record(stage: str, **extra: object) -> None:
        write_json(process / "experiment_log.json", {"timestamp": utc_now(), "stage": stage, **extra})

    def run(command: list[str]) -> None:
        append_jsonl(commands, {"timestamp": utc_now(), "command": command})
        print("+", " ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)

    try:
        write_json(process / "build_manifest.json", {
            "schema_version": 1,
            "source_files": source_manifest(),
            "license_acknowledged": True,
            "inputs": ["question.zip", "submission_example.zip"],
        })
        runtime = {"python": sys.version, "platform": platform.platform()}
        try:
            import torch
            runtime.update({"torch": torch.__version__, "cuda": torch.version.cuda, "cuda_available": torch.cuda.is_available()})
            if torch.cuda.is_available():
                runtime["gpu"] = torch.cuda.get_device_name(0)
        except Exception as error:
            runtime["torch_probe_error"] = type(error).__name__
        write_json(process / "runtime.json", runtime)
        record("started", backend="hunyuan", load_mode="resident")

        third_party = ROOT / "third_party"
        if not (third_party / "sam2").is_dir() or not (third_party / "Hunyuan3D-2.1").is_dir():
            run([sys.executable, "scripts/bootstrap_models.py", "--root", str(third_party), "--sam2", "--hunyuan", "--accept-hunyuan-license"])
        run([
            "asset-baseline", "--config", "config/default.yaml",
            "--set", f"question_zip={question}",
            "--set", f"submission_example_zip={example}",
            "--set", f"output_root={output_root}",
            "--set", f"run_name={args.run_name}",
            "run",
        ])
        package = run_root / "packages" / "asset_baseline_submission.zip"
        validation = json.loads((run_root / "reports" / "validation.json").read_text(encoding="utf-8"))
        package_manifest = json.loads((run_root / "manifests" / "package.json").read_text(encoding="utf-8"))
        shutil.copy2(package, output_root / "asset_baseline_submission.zip")
        write_json(process / "metrics.json", {
            "valid": validation["valid"],
            "valid_tasks": validation["valid_tasks"],
            "package_sha256": package_manifest["sha256"],
            "package_bytes": package_manifest["bytes"],
        })
        record("completed", valid=validation["valid"], valid_tasks=validation["valid_tasks"], package_sha256=package_manifest["sha256"])
    except BaseException as error:
        record("failed", error_type=type(error).__name__, error=str(error))
        raise


if __name__ == "__main__":
    main()
