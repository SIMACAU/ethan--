#!/usr/bin/env python3
"""Build the locked submission from the two bundled intermediate archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = "submission_example/submission"
BASE_SHA256 = "dc56dfdf29e81f4e0b4fd300b8e84acea3535a486dc6d26051123252209f3ada"
DONOR_SHA256 = "573ac2792f6df5650ee9b47c37dec052f68065c74a2133e6f4357fa9dd63dadf"
FINAL_SHA256 = "2e979d08d10a785e0c47a4a1ba923131a52c8e53970bb0578f815893585e8d4b"
FINAL_BYTES = 19_539_975
FINAL_MEMBERS = 56
REPLACED_MEMBERS = tuple(
    f"{ARCHIVE_ROOT}/{task_id}/{task_id}.usd" for task_id in ("item_029", "item_030")
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_member_name(name: str) -> None:
    value = PurePosixPath(name)
    if (
        not name
        or value.is_absolute()
        or ".." in value.parts
        or "__MACOSX" in value.parts
        or any(part.startswith("._") for part in value.parts)
    ):
        raise ValueError(f"unsafe ZIP member: {name!r}")


def read_members(path: Path) -> dict[str, bytes]:
    if not path.is_file():
        raise FileNotFoundError(path)
    result: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        corrupt = archive.testzip()
        if corrupt is not None:
            raise ValueError(f"CRC failure in {path.name}: {corrupt}")
        for info in archive.infolist():
            if info.is_dir():
                continue
            _check_member_name(info.filename)
            if info.filename in result:
                raise ValueError(f"duplicate ZIP member: {info.filename}")
            result[info.filename] = archive.read(info)
    return result


def require_hash(path: Path, expected: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"input hash drift for {path.name}: expected {expected}, got {actual}")


def validate_layout(members: dict[str, bytes]) -> None:
    if len(members) != FINAL_MEMBERS:
        raise ValueError(f"member count is {len(members)}, expected {FINAL_MEMBERS}")
    expected_tasks = {f"item_{index:03d}" for index in range(1, 35)}
    observed_tasks = {
        PurePosixPath(name).parts[2]
        for name in members
        if len(PurePosixPath(name).parts) >= 4
        and PurePosixPath(name).parts[:2] == ("submission_example", "submission")
    }
    if observed_tasks != expected_tasks:
        raise ValueError(f"task mismatch: missing={sorted(expected_tasks-observed_tasks)}, extra={sorted(observed_tasks-expected_tasks)}")
    for task_id in expected_tasks:
        member = f"{ARCHIVE_ROOT}/{task_id}/{task_id}.usd"
        payload = members.get(member)
        if payload is None or not payload.startswith(b"PXR-USDC"):
            raise ValueError(f"missing or non-USDC task asset: {member}")


def compose(base_path: Path, donor_path: Path) -> tuple[dict[str, bytes], dict[str, str]]:
    require_hash(base_path, BASE_SHA256)
    require_hash(donor_path, DONOR_SHA256)
    members = read_members(base_path)
    donor = read_members(donor_path)
    origins = {name: "base" for name in members}
    for name in REPLACED_MEMBERS:
        if name not in members or name not in donor:
            raise ValueError(f"missing replacement member: {name}")
        members[name] = donor[name]
        origins[name] = "donor"
    validate_layout(members)
    return members, origins


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def write_package(members: dict[str, bytes], output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".part")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted(members):
                archive.writestr(_zip_info(name), members[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def build(base_path: Path, donor_path: Path, output: Path) -> dict[str, Any]:
    members, origins = compose(base_path, donor_path)
    write_package(members, output)
    if sha256(output) != FINAL_SHA256 or output.stat().st_size != FINAL_BYTES:
        raise RuntimeError("built package is not byte-identical to the locked candidate")
    if zipfile.ZipFile(output).testzip() is not None:
        raise RuntimeError("built package has a CRC failure")
    return {
        "schema_version": 1,
        "method": "base_all_members_plus_donor_two_usd_members",
        "inputs": {
            "base": {"sha256": BASE_SHA256, "members": len(read_members(base_path))},
            "donor": {"sha256": DONOR_SHA256, "members": len(read_members(donor_path))},
        },
        "replaced_members": list(REPLACED_MEMBERS),
        "member_lineage": [
            {
                "name": name,
                "origin": origins[name],
                "bytes": len(members[name]),
                "sha256": hashlib.sha256(members[name]).hexdigest(),
            }
            for name in sorted(members)
        ],
        "output": {"sha256": FINAL_SHA256, "bytes": FINAL_BYTES, "members": FINAL_MEMBERS},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=ROOT / "artifacts/intermediate/base_submission.zip")
    parser.add_argument("--donor", type=Path, default=ROOT / "artifacts/intermediate/donor_submission.zip")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = build(args.base.resolve(), args.donor.resolve(), args.output.resolve())
    report_path = args.report.resolve() if args.report else args.output.resolve().with_name("rebuild_report.json")
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite {report_path}")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
