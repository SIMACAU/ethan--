"""Blender-side GLB cleanup and simulation-ready USD packaging.

Run with:
  blender --background --python blender_package_usd.py -- INPUT OUTPUT ITEM LABEL ...
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from pxr import Usd, UsdGeom, UsdPhysics


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("input_glb", type=Path)
    parser.add_argument("output_usd", type=Path)
    parser.add_argument("item_id")
    parser.add_argument("label")
    parser.add_argument("--target-max-dimension", type=float, default=1.0)
    parser.add_argument("--mass-kg", type=float, default=1.0)
    parser.add_argument("--max-faces", type=int, default=200_000)
    parser.add_argument("--static", action="store_true")
    return parser.parse_args(argv)


def safe_prim_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not value or value[0].isdigit():
        value = f"asset_{value}"
    return value


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def world_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        for corner in obj.bound_box
    ]
    minimum = Vector(
        (
            min(point.x for point in points),
            min(point.y for point in points),
            min(point.z for point in points),
        )
    )
    maximum = Vector(
        (
            max(point.x for point in points),
            max(point.y for point in points),
            max(point.z for point in points),
        )
    )
    return minimum, maximum


def decimate_meshes(objects: list[bpy.types.Object], max_faces: int) -> None:
    total_faces = sum(len(obj.data.polygons) for obj in objects)
    if total_faces <= max_faces or total_faces == 0:
        return
    ratio = max(max_faces / total_faces, 0.01)
    for obj in objects:
        if len(obj.data.polygons) < 100:
            continue
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        modifier = obj.modifiers.new(name="AutomaticDecimation", type="DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = ratio
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        obj.select_set(False)


def package_scene(args: argparse.Namespace) -> None:
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(args.input_glb.resolve()))

    for obj in list(bpy.context.scene.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"No mesh objects imported from {args.input_glb}")

    for obj in meshes:
        obj.data.validate(clean_customdata=False)
        obj.data.update()
    decimate_meshes(meshes, args.max_faces)

    root = bpy.data.objects.new("Asset", None)
    bpy.context.scene.collection.objects.link(root)
    for obj in list(bpy.context.scene.objects):
        if obj == root or obj.parent is not None:
            continue
        world_matrix = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = world_matrix

    minimum, maximum = world_bounds(meshes)
    size = maximum - minimum
    current_max_dimension = max(size)
    if current_max_dimension <= 0:
        raise RuntimeError("Imported mesh has a degenerate bounding box")
    scale = args.target_max_dimension / current_max_dimension
    root.scale = (scale, scale, scale)
    root.location = (
        -(minimum.x + maximum.x) * 0.5 * scale,
        -(minimum.y + maximum.y) * 0.5 * scale,
        -minimum.z * scale,
    )
    root["item_id"] = args.item_id
    root["semantic_label"] = args.label
    root["mass_kg"] = float(args.mass_kg)
    root["source_pipeline"] = "automatic_video_photogrammetry"

    output = args.output_usd.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    root_prim_name = safe_prim_name(args.item_id)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    bpy.ops.wm.usd_export(
        filepath=str(output),
        export_animation=False,
        export_meshes=True,
        export_lights=False,
        export_cameras=False,
        export_curves=False,
        export_volumes=False,
        export_hair=False,
        export_materials=True,
        export_uvmaps=True,
        export_normals=True,
        export_textures_mode="NEW",
        overwrite_textures=True,
        relative_paths=True,
        generate_preview_surface=True,
        generate_materialx_network=False,
        export_custom_properties=True,
        triangulate_meshes=True,
        meters_per_unit=1.0,
        root_prim_path=f"/{root_prim_name}",
        allow_unicode=True,
    )

    stage = Usd.Stage.Open(str(output))
    if stage is None:
        raise RuntimeError(f"Blender exported an unreadable USD: {output}")
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    root_prim = stage.GetPrimAtPath(f"/{root_prim_name}")
    if not root_prim:
        raise RuntimeError(f"USD root prim is missing: /{root_prim_name}")
    stage.SetDefaultPrim(root_prim)

    mesh_count = 0
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh_count += 1
        UsdPhysics.CollisionAPI.Apply(prim)
        mesh_collision = UsdPhysics.MeshCollisionAPI.Apply(prim)
        mesh_collision.CreateApproximationAttr().Set("convexHull")

    if mesh_count == 0:
        raise RuntimeError("USD contains no mesh prims")
    if not args.static:
        rigid_body = UsdPhysics.RigidBodyAPI.Apply(root_prim)
        rigid_body.CreateRigidBodyEnabledAttr().Set(True)
        mass = UsdPhysics.MassAPI.Apply(root_prim)
        mass.CreateMassAttr().Set(float(args.mass_kg))

    root_prim.SetCustomDataByKey("itemId", args.item_id)
    root_prim.SetCustomDataByKey("semanticLabel", args.label)
    root_prim.SetCustomDataByKey("pipeline", "automatic_video_photogrammetry")
    stage.GetRootLayer().Save()

    verification = Usd.Stage.Open(str(output))
    if verification is None or not verification.GetDefaultPrim():
        raise RuntimeError(f"Final USD verification failed: {output}")
    print(
        f"USD packaged: {output} | meshes={mesh_count} | "
        f"target_max_dimension={args.target_max_dimension}m"
    )


if __name__ == "__main__":
    package_scene(parse_args())
