import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from pxr import Usd, UsdGeom, UsdPhysics

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
item_id = argv[0]
stem = argv[1]
root = Path(r"C:\Users\MACAU\Desktop\天池")
usd = root / "output" / "submission" / "submission" / item_id / f"{item_id}.usd"
out_dir = root / "work" / "preview_pack34"


def setup_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.usd_import(filepath=str(usd))
    pts = []
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            pts += [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    mins = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    maxs = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (mins + maxs) / 2
    size = maxs - mins
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 800
    scene.render.resolution_y = 500
    scene.world = bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.86, 0.87, 0.88, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.2
    sun.rotation_euler = (math.radians(50), 0, math.radians(25))
    scene.collection.objects.link(sun)
    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "SUN"))
    fill.data.energy = 1.0
    fill.rotation_euler = (math.radians(20), math.radians(-30), 0)
    scene.collection.objects.link(fill)
    return center, size


def add_cam(center, offset):
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = center + offset
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


center, size = setup_scene()
span = max(size.x, size.y, size.z, 0.04)
add_cam(center, Vector((span * 1.4, -span * 2.1, span * 0.85)))
bpy.context.scene.render.filepath = str(out_dir / f"{stem}.png")
bpy.ops.render.render(write_still=True)

for obj in list(bpy.data.objects):
    if obj.type == "CAMERA":
        bpy.data.objects.remove(obj, do_unlink=True)
add_cam(center, Vector((span * 0.2, -span * 2.6, span * 0.35)))
bpy.context.scene.render.filepath = str(out_dir / f"{stem}_side.png")
bpy.ops.render.render(write_still=True)

stage = Usd.Stage.Open(str(usd))
bbox = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render], True)
rng = bbox.ComputeWorldBound(stage.GetPrimAtPath(f"/{item_id}")).GetRange()
mn, mx = rng.GetMin(), rng.GetMax()
print("bbox", tuple(round(mx[i] - mn[i], 4) for i in range(3)))
print("z", round(mn[2], 4), round(mx[2], 4))
print(
    "joints",
    [
        str(prim.GetPath())
        for prim in stage.Traverse()
        if prim.IsA(UsdPhysics.RevoluteJoint) or prim.IsA(UsdPhysics.PrismaticJoint)
    ],
)
