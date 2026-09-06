"""Validate every competition USD with Blender's bundled OpenUSD runtime."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from pxr import Usd, UsdGeom, UsdPhysics, UsdShade


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("submission_root", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--expected-count", type=int, default=34)
    return parser.parse_args(argv)


def validate_stage(path: Path) -> dict:
    errors: list[str] = []
    stage = Usd.Stage.Open(str(path))
    if stage is None:
        return {"path": str(path), "errors": ["stage could not be opened"]}

    default_prim = stage.GetDefaultPrim()
    if not default_prim:
        errors.append("missing default prim")

    meshes = [
        prim for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh)
    ]
    materials = [
        prim for prim in stage.Traverse() if prim.IsA(UsdShade.Material)
    ]
    collisions = [
        prim
        for prim in stage.Traverse()
        if prim.HasAPI(UsdPhysics.CollisionAPI)
    ]
    rigid_bodies = [
        prim
        for prim in stage.Traverse()
        if prim.HasAPI(UsdPhysics.RigidBodyAPI)
    ]
    if not meshes:
        errors.append("contains no mesh prim")
    if not collisions:
        errors.append("contains no collision API")

    dimensions = [0.0, 0.0, 0.0]
    if default_prim:
        cache = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(),
            [UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
            useExtentsHint=True,
        )
        bounds = cache.ComputeWorldBound(default_prim).ComputeAlignedRange()
        size = bounds.GetSize()
        dimensions = [float(size[index]) for index in range(3)]
        if not all(math.isfinite(value) and value > 0 for value in dimensions):
            errors.append(f"invalid world dimensions: {dimensions}")

    unresolved_layers = [
        layer.identifier
        for layer in stage.GetUsedLayers()
        if not layer.anonymous and not Path(layer.realPath).exists()
    ]
    if unresolved_layers:
        errors.append(f"unresolved layers: {unresolved_layers}")

    return {
        "path": str(path),
        "default_prim": str(default_prim.GetPath()) if default_prim else None,
        "mesh_count": len(meshes),
        "material_count": len(materials),
        "collision_count": len(collisions),
        "rigid_body_count": len(rigid_bodies),
        "dimensions_m": dimensions,
        "errors": errors,
    }


def main() -> None:
    args = parse_args()
    submission_root = args.submission_root.resolve()
    expected_ids = {f"item_{index:03d}" for index in range(1, args.expected_count + 1)}
    found_ids = {
        path.name for path in submission_root.glob("item_*") if path.is_dir()
    }
    package_errors: list[str] = []
    if found_ids != expected_ids:
        missing = sorted(expected_ids - found_ids)
        unexpected = sorted(found_ids - expected_ids)
        if missing:
            package_errors.append(f"missing item folders: {missing}")
        if unexpected:
            package_errors.append(f"unexpected item folders: {unexpected}")

    stages: list[dict] = []
    for item_id in sorted(found_ids):
        expected_usd = submission_root / item_id / f"{item_id}.usd"
        if not expected_usd.exists():
            stages.append(
                {"path": str(expected_usd), "errors": ["required USD is missing"]}
            )
            continue
        stages.append(validate_stage(expected_usd))

    result = {
        "submission_root": str(submission_root),
        "expected_count": args.expected_count,
        "found_count": len(found_ids),
        "package_errors": package_errors,
        "stages": stages,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    errors = package_errors + [
        error for stage in stages for error in stage.get("errors", [])
    ]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(f"USD validation found {len(errors)} error(s)")


if __name__ == "__main__":
    main()
