#!/usr/bin/env python3
"""Create and fully validate the locked candidate without GPU inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import rebuild_submission
import validate_submission


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_root.resolve()
    if output.exists():
        raise FileExistsError(f"choose a new output directory: {output}")
    output.mkdir(parents=True)
    root = Path(__file__).resolve().parents[1]
    package = output / "submission.zip"
    rebuild = rebuild_submission.build(
        root / "artifacts/intermediate/base_submission.zip",
        root / "artifacts/intermediate/donor_submission.zip",
        package,
    )
    validation = validate_submission.validate_package(package)
    (output / "rebuild_report.json").write_text(json.dumps(rebuild, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "validation_report.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not validation["valid"]:
        raise RuntimeError("candidate failed the non-GPU validation gate")
    print(json.dumps({"package": "submission.zip", "sha256": rebuild_submission.FINAL_SHA256, "valid_tasks": validation["valid_tasks"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
