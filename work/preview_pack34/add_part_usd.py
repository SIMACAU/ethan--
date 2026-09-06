"""Add a small prim to an existing pack28 USD without rebuilding materials."""

from __future__ import annotations

import math

from pxr import Gf, Usd, UsdGeom, UsdPhysics, Vt


def _display_color(mesh: UsdGeom.Mesh, color: tuple[float, float, float]) -> None:
    UsdGeom.Gprim(mesh.GetPrim()).CreateDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*color)]))


def _collision(mesh: UsdGeom.Mesh) -> None:
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
    collision = UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim())
    collision.CreateApproximationAttr().Set("convexHull")


def _box_mesh(stage: Usd.Stage, path: str, size: tuple[float, float, float], color: tuple[float, float, float]) -> UsdGeom.Mesh:
    hx, hy, hz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
    points = [
        Gf.Vec3f(-hx, -hy, -hz),
        Gf.Vec3f(hx, -hy, -hz),
        Gf.Vec3f(hx, hy, -hz),
        Gf.Vec3f(-hx, hy, -hz),
        Gf.Vec3f(-hx, -hy, hz),
        Gf.Vec3f(hx, -hy, hz),
        Gf.Vec3f(hx, hy, hz),
        Gf.Vec3f(-hx, hy, hz),
    ]
    counts = [4, 4, 4, 4, 4, 4]
    indices = [
        0, 1, 2, 3,
        4, 7, 6, 5,
        0, 4, 5, 1,
        1, 5, 6, 2,
        2, 6, 7, 3,
        3, 7, 4, 0,
    ]
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateExtentAttr([Gf.Vec3f(-hx, -hy, -hz), Gf.Vec3f(hx, hy, hz)])
    mesh.CreateSubdivisionSchemeAttr().Set("none")
    _display_color(mesh, color)
    _collision(mesh)
    return mesh


def _cylinder_mesh(
    stage: Usd.Stage,
    path: str,
    radius: float,
    height: float,
    color: tuple[float, float, float],
    segs: int = 24,
) -> UsdGeom.Mesh:
    hz = height / 2.0
    points = []
    for ring in (-hz, hz):
        for i in range(segs):
            ang = 6.283185307179586 * i / segs
            points.append(Gf.Vec3f(radius * math.cos(ang), radius * math.sin(ang), ring))
    counts = []
    indices = []
    for i in range(segs):
        j = (i + 1) % segs
        counts.append(4)
        indices.extend([i, j, segs + j, segs + i])
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateExtentAttr([Gf.Vec3f(-radius, -radius, -hz), Gf.Vec3f(radius, radius, hz)])
    mesh.CreateSubdivisionSchemeAttr().Set("none")
    _display_color(mesh, color)
    _collision(mesh)
    return mesh


def add_box(
    usd_path: str,
    xform_path: str,
    translate: tuple[float, float, float],
    size: tuple[float, float, float],
    color: tuple[float, float, float] = (0.10, 0.10, 0.11),
) -> None:
    stage = Usd.Stage.Open(usd_path)
    if stage is None:
        raise RuntimeError(usd_path)
    if stage.GetPrimAtPath(xform_path):
        raise RuntimeError(f"already exists {xform_path}")
    xf = UsdGeom.Xform.Define(stage, xform_path)
    xf.AddTranslateOp().Set(Gf.Vec3d(*translate))
    _box_mesh(stage, f"{xform_path}/Cube", size, color)
    stage.GetRootLayer().Save()
    print("added", xform_path, "->", usd_path)


def add_cylinder(
    usd_path: str,
    xform_path: str,
    translate: tuple[float, float, float],
    radius: float,
    height: float,
    color: tuple[float, float, float],
    rotate_xyz: tuple[float, float, float] = (0.0, 90.0, 0.0),
) -> None:
    stage = Usd.Stage.Open(usd_path)
    if stage is None:
        raise RuntimeError(usd_path)
    if stage.GetPrimAtPath(xform_path):
        raise RuntimeError(f"already exists {xform_path}")
    xf = UsdGeom.Xform.Define(stage, xform_path)
    xf.AddTranslateOp().Set(Gf.Vec3d(*translate))
    xf.AddRotateXYZOp().Set(Gf.Vec3f(*rotate_xyz))
    _cylinder_mesh(stage, f"{xform_path}/Cylinder", radius, height, color)
    stage.GetRootLayer().Save()
    print("added", xform_path, "->", usd_path)
