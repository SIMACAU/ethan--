from __future__ import annotations

from pathlib import Path
from typing import Any

from pxr import Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

from .usd_asset import simulate_mjcf
from .util import utc_now


def _validate_usd(task_id: str, asset: Path) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    counts = {"gprims": 0, "colliders": 0, "rigid_bodies": 0, "physics_scenes": 0, "textures": 0}
    stage = Usd.Stage.Open(str(asset))
    if stage is None:
        return ["Usd.Stage.Open returned None"], counts
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
        if prim.IsA(UsdShade.Shader):
            shader = UsdShade.Shader(prim)
            file_input = shader.GetInput("file")
            value = file_input.Get() if file_input else None
            if isinstance(value, Sdf.AssetPath) and value.path:
                counts["textures"] += 1
                if Path(value.path).is_absolute() or value.path.startswith(("http://", "https://")):
                    errors.append(f"non-local texture reference: {value.path}")
                elif not (asset.parent / value.path).is_file():
                    errors.append(f"missing texture reference: {value.path}")
    if counts["gprims"] < 1:
        errors.append("no renderable geometry")
    if counts["physics_scenes"] != 1:
        errors.append(f"expected one physics scene, found {counts['physics_scenes']}")
    if counts["colliders"] < 1 or counts["rigid_bodies"] < 1:
        errors.append("missing conservative collision/rigid-body APIs")
    return errors, counts


def validate_submission_tree(submission: Path, physics_root: Path, steps: int) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    all_errors: list[str] = []
    for index in range(1, 35):
        task_id = f"item_{index:03d}"
        usd = submission / task_id / f"{task_id}.usd"
        mjcf = physics_root / task_id / f"{task_id}.xml"
        errors, counts = _validate_usd(task_id, usd)
        simulation: dict[str, Any] | None = None
        try:
            simulation = simulate_mjcf(mjcf, steps)
        except Exception as error:
            errors.append(f"MuJoCo: {type(error).__name__}: {error}")
        all_errors.extend(f"{task_id}: {error}" for error in errors)
        records.append({"task_id": task_id, "usd": str(usd), "mjcf": str(mjcf), "valid": not errors, "errors": errors, "counts": counts, "simulation": simulation})
    return {"created_at": utc_now(), "valid": not all_errors, "task_count": len(records), "valid_tasks": sum(record["valid"] for record in records), "simulation_steps": steps, "errors": all_errors, "tasks": records}
