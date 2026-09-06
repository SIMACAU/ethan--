from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
import trimesh
from PIL import Image
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

from .util import write_json


def _texture_coordinates(mesh: trimesh.Trimesh) -> np.ndarray:
    visual = getattr(mesh, "visual", None)
    uv = getattr(visual, "uv", None)
    if uv is not None and len(uv) == len(mesh.vertices):
        return np.asarray(uv, dtype=np.float32)
    points = np.asarray(mesh.vertices, dtype=np.float64)
    lower, upper = points[:, :2].min(axis=0), points[:, :2].max(axis=0)
    return ((points[:, :2] - lower) / np.maximum(upper - lower, 1e-6)).astype(np.float32)


def _material(stage: Usd.Stage, texture: str) -> UsdShade.Material:
    material = UsdShade.Material.Define(stage, "/World/Materials/Appearance")
    shader = UsdShade.Shader.Define(stage, "/World/Materials/Appearance/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.55)
    texture_node = UsdShade.Shader.Define(stage, "/World/Materials/Appearance/Texture")
    texture_node.CreateIdAttr("UsdUVTexture")
    texture_node.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(texture))
    texture_node.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
    reader = UsdShade.Shader.Define(stage, "/World/Materials/Appearance/ST")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    texture_node.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
    texture_node.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture_node.ConnectableAPI(), "rgb")
    shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def _write_texture(mesh: trimesh.Trimesh, conditioning_image: Path, destination: Path) -> str:
    """Persist the generated GLB albedo when available, otherwise use the input view.

    A high-profile Hunyuan result carries a UV texture in its GLB.  Keeping that
    image is essential: copying the conditioning frame unconditionally would
    quietly discard Hunyuan Paint's result.
    """
    material = getattr(getattr(mesh, "visual", None), "material", None)
    generated = getattr(material, "image", None)
    if generated is not None:
        if isinstance(generated, Image.Image):
            generated.convert("RGBA").save(destination)
        else:
            Image.fromarray(np.asarray(generated)).convert("RGBA").save(destination)
        return "reconstructed_mesh_albedo"
    shutil.copy2(conditioning_image, destination)
    return "conditioning_image_fallback"


def _write_mjcf(task_id: str, extent: np.ndarray, output: Path, physics: dict[str, Any]) -> None:
    size = np.maximum(extent / 2.0, 0.015)
    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<mujoco model="{task_id}">
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <worldbody>
    <body name="asset" pos="0 0 1">
      <freejoint/>
      <geom type="box" size="{size[0]:.7f} {size[1]:.7f} {size[2]:.7f}" mass="{float(physics['default_mass_kg']):.7f}" friction="{float(physics['friction']):.7f} 0.02 0.002"/>
    </body>
  </worldbody>
</mujoco>
'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(xml, encoding="utf-8")


def write_usd_asset(task_id: str, mesh_path: Path, conditioning_image: Path, output_dir: Path, physics: dict[str, Any]) -> dict[str, Any]:
    """Create a self-contained binary USD with visual mesh and collision data."""
    mesh = trimesh.load(mesh_path, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ValueError(f"invalid reconstructed mesh: {mesh_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    texture_dir = output_dir / "textures"
    texture_dir.mkdir(exist_ok=True)
    texture_path = texture_dir / "texture_00.png"
    texture_source = _write_texture(mesh, conditioning_image, texture_path)
    usd_path = output_dir / f"{task_id}.usd"
    stage = Usd.Stage.CreateNew(str(usd_path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    asset = UsdGeom.Xform.Define(stage, "/World/Asset")
    UsdPhysics.RigidBodyAPI.Apply(asset.GetPrim())
    mass = UsdPhysics.MassAPI.Apply(asset.GetPrim())
    mass.CreateMassAttr(float(physics["default_mass_kg"]))
    visual = UsdGeom.Mesh.Define(stage, "/World/Asset/Visual")
    points = np.asarray(mesh.vertices, dtype=np.float32)
    visual.CreatePointsAttr([Gf.Vec3f(float(point[0]), float(point[1]), float(point[2])) for point in points])
    visual.CreateFaceVertexCountsAttr([3] * len(mesh.faces))
    visual.CreateFaceVertexIndicesAttr([int(index) for face in mesh.faces for index in face])
    visual.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    visual.CreateExtentAttr([
        Gf.Vec3f(float(mesh.bounds[0, 0]), float(mesh.bounds[0, 1]), float(mesh.bounds[0, 2])),
        Gf.Vec3f(float(mesh.bounds[1, 0]), float(mesh.bounds[1, 1]), float(mesh.bounds[1, 2])),
    ])
    uv = _texture_coordinates(mesh)
    primvars = UsdGeom.PrimvarsAPI(visual)
    st = primvars.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    st.Set([Gf.Vec2f(float(value[0]), float(value[1])) for value in uv])
    UsdShade.MaterialBindingAPI.Apply(visual.GetPrim()).Bind(_material(stage, "textures/texture_00.png"))
    collision_mode = str(physics.get("collision_mode", "convex_hull"))
    extent = np.asarray(mesh.extents, dtype=np.float32)
    if collision_mode == "convex_hull":
        # A convex hull follows the reconstructed silhouette much more closely
        # than one axis-aligned cube, while remaining a stable dynamic shape in
        # USD physics engines.  The visible mesh stays the render mesh.
        UsdPhysics.CollisionAPI.Apply(visual.GetPrim())
        collision = UsdPhysics.MeshCollisionAPI.Apply(visual.GetPrim())
        collision.CreateApproximationAttr().Set(UsdPhysics.Tokens.convexHull)
    elif collision_mode == "bounding_box":
        collider = UsdGeom.Cube.Define(stage, "/World/Asset/Collision")
        collider.CreateSizeAttr(1.0)
        collider.AddScaleOp().Set(Gf.Vec3f(float(extent[0] / 2.0), float(extent[1] / 2.0), float(extent[2] / 2.0)))
        collider.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
        UsdPhysics.CollisionAPI.Apply(collider.GetPrim())
    else:
        raise ValueError(f"unsupported collision_mode: {collision_mode}")
    stage.GetRootLayer().Save()
    if not usd_path.is_file() or Usd.Stage.Open(str(usd_path)) is None:
        raise RuntimeError(f"USD write/reopen failed: {usd_path}")
    mjcf_path = output_dir.parent.parent / "physics" / task_id / f"{task_id}.xml"
    _write_mjcf(task_id, extent, mjcf_path, physics)
    return {"task_id": task_id, "usd": str(usd_path), "texture": str(texture_path), "texture_source": texture_source, "collision_mode": collision_mode, "mjcf": str(mjcf_path), "extent": [float(value) for value in extent]}


def simulate_mjcf(path: Path, steps: int) -> dict[str, Any]:
    model = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(model)
    for _ in range(steps):
        mujoco.mj_step(model, data)
    if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
        raise RuntimeError(f"non-finite MuJoCo state: {path}")
    return {"mjcf": str(path), "steps": steps, "qpos": [float(value) for value in data.qpos], "qvel": [float(value) for value in data.qvel]}
