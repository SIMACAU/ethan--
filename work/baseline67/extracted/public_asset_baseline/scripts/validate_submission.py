#!/usr/bin/env python3
"""Perform deterministic ZIP, OpenUSD and lightweight physics checks without GPU."""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import mujoco
from pxr import Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

import rebuild_submission


def _extract(members: dict[str, bytes], root: Path) -> Path:
    for name, payload in members.items():
        target = (root / name).resolve()
        if root.resolve() not in target.parents:
            raise ValueError(f"unsafe extraction target: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return root / rebuild_submission.ARCHIVE_ROOT


def _physics_probe(points: np.ndarray) -> dict[str, float]:
    lower, upper = points.min(axis=0), points.max(axis=0)
    size = np.maximum((upper - lower) / 2.0, 0.015)
    xml = f'''<mujoco model="asset"><option timestep="0.002" gravity="0 0 -9.81"/><worldbody><body pos="0 0 1"><freejoint/><geom type="box" size="{size[0]:.7f} {size[1]:.7f} {size[2]:.7f}" mass="1"/></body></worldbody></mujoco>'''
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    for _ in range(120):
        mujoco.mj_step(model, data)
    if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
        raise ValueError("non-finite lightweight physics state")
    return {"steps": 120, "z": float(data.qpos[2]), "vertical_velocity": float(data.qvel[2])}


def _validate_asset(task_id: str, asset: Path) -> dict[str, Any]:
    errors: list[str] = []
    counts = {"gprims": 0, "colliders": 0, "rigid_bodies": 0, "physics_scenes": 0, "textures": 0}
    points: list[tuple[float, float, float]] = []
    stage = Usd.Stage.Open(str(asset))
    if stage is None:
        return {"task_id": task_id, "valid": False, "errors": ["Usd.Stage.Open returned None"], "counts": counts}
    if stage.GetDefaultPrim().GetPath() != Sdf.Path("/World"):
        errors.append("default prim is not /World")
    if UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z:
        errors.append("up axis is not Z")
    if abs(float(UsdGeom.GetStageMetersPerUnit(stage)) - 1.0) > 1e-9:
        errors.append("meters per unit is not 1")
    for prim in stage.Traverse():
        counts["gprims"] += int(prim.IsA(UsdGeom.Gprim))
        counts["colliders"] += int(prim.HasAPI(UsdPhysics.CollisionAPI))
        counts["rigid_bodies"] += int(prim.HasAPI(UsdPhysics.RigidBodyAPI))
        counts["physics_scenes"] += int(prim.IsA(UsdPhysics.Scene))
        if prim.IsA(UsdGeom.Gprim):
            bound = UsdGeom.Boundable(prim).ComputeWorldBound(
                Usd.TimeCode.Default(), UsdGeom.Tokens.default_
            ).ComputeAlignedRange()
            if not bound.IsEmpty():
                lower, upper = bound.GetMin(), bound.GetMax()
                points.extend(
                    [
                        (float(lower[0]), float(lower[1]), float(lower[2])),
                        (float(upper[0]), float(upper[1]), float(upper[2])),
                    ]
                )
        if prim.IsA(UsdShade.Shader):
            shader = UsdShade.Shader(prim)
            file_input = shader.GetInput("file")
            value = file_input.Get() if file_input else None
            if isinstance(value, Sdf.AssetPath) and value.path:
                counts["textures"] += 1
                if Path(value.path).is_absolute() or value.path.startswith(("http://", "https://")):
                    errors.append(f"non-local texture: {value.path}")
                elif not (asset.parent / value.path).is_file():
                    errors.append(f"missing texture: {value.path}")
    if not counts["gprims"] or not points:
        errors.append("no renderable geometry")
    if counts["physics_scenes"] != 1:
        errors.append(f"expected one physics scene, found {counts['physics_scenes']}")
    if not counts["colliders"]:
        errors.append("missing collision API")
    physics = None
    if not errors and counts["rigid_bodies"]:
        try:
            physics = _physics_probe(np.asarray(points, dtype=np.float64))
        except Exception as error:
            errors.append(f"physics probe: {type(error).__name__}: {error}")
    elif not errors:
        physics = {"mode": "static_scene", "steps": 0}
    return {"task_id": task_id, "valid": not errors, "errors": errors, "counts": counts, "physics_probe": physics}


def validate_package(package: Path) -> dict[str, Any]:
    if rebuild_submission.sha256(package) != rebuild_submission.FINAL_SHA256:
        raise ValueError("candidate hash is not the locked submission hash")
    members = rebuild_submission.read_members(package)
    rebuild_submission.validate_layout(members)
    with tempfile.TemporaryDirectory(prefix="asset-baseline-validation-") as raw:
        submission = _extract(members, Path(raw))
        tasks = [
            _validate_asset(task_id, submission / task_id / f"{task_id}.usd")
            for task_id in (f"item_{index:03d}" for index in range(1, 35))
        ]
    errors = [f"{task['task_id']}: {message}" for task in tasks for message in task["errors"]]
    return {
        "schema_version": 1,
        "package_sha256": rebuild_submission.FINAL_SHA256,
        "package_bytes": package.stat().st_size,
        "zip_crc": "pass",
        "task_count": len(tasks),
        "valid_tasks": sum(task["valid"] for task in tasks),
        "physics_probe_steps": 120,
        "valid": not errors,
        "errors": errors,
        "tasks": tasks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError(f"refusing to overwrite {args.report}")
    report = validate_package(args.package.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "tasks"}, ensure_ascii=False, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
