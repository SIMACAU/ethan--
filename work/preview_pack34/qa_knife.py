import bpy, math
from mathutils import Vector
from pathlib import Path
from pxr import Usd, UsdGeom, UsdPhysics

usd = r"C:\Users\MACAU\Desktop\天池\output\submission\submission\item_010\item_010.usd"
out_dir = Path(r"C:\Users\MACAU\Desktop\天池\work\preview_pack34")

def setup_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.usd_import(filepath=usd)
    pts = []
    for o in bpy.data.objects:
        if o.type == "MESH":
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctr = (mn + mx) / 2
    size = mx - mn
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = 800
    sc.render.resolution_y = 500
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.86, 0.87, 0.88, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.2
    sun.rotation_euler = (math.radians(50), 0, math.radians(25))
    sc.collection.objects.link(sun)
    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "SUN"))
    fill.data.energy = 1.0
    fill.rotation_euler = (math.radians(20), math.radians(-30), 0)
    sc.collection.objects.link(fill)
    return ctr, size

def add_cam(ctr, offset):
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = ctr + offset
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam

ctr, size = setup_scene()
span = max(size.x, size.y, size.z, 0.04)
add_cam(ctr, Vector((span * 1.4, -span * 2.1, span * 0.85)))
bpy.context.scene.render.filepath = str(out_dir / "item_010_v9.png")
bpy.ops.render.render(write_still=True)

for obj in list(bpy.data.objects):
    if obj.type == "CAMERA":
        bpy.data.objects.remove(obj, do_unlink=True)
add_cam(ctr, Vector((0.0, -span * 2.8, span * 0.12)))
bpy.context.scene.render.filepath = str(out_dir / "item_010_v9_side.png")
bpy.ops.render.render(write_still=True)

for obj in list(bpy.data.objects):
    if obj.type == "CAMERA":
        bpy.data.objects.remove(obj, do_unlink=True)
add_cam(ctr, Vector((0.0, span * 0.05, span * 2.6)))
bpy.context.scene.render.filepath = str(out_dir / "item_010_v9_top.png")
bpy.ops.render.render(write_still=True)

s = Usd.Stage.Open(usd)
bbox = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render], True)
rng = bbox.ComputeWorldBound(s.GetPrimAtPath("/item_010")).GetRange()
mn, mx = rng.GetMin(), rng.GetMax()
print("bbox", tuple(round(mx[i]-mn[i],4) for i in range(3)))
print("z", round(mn[2],4), round(mx[2],4))
print("joints", [str(p.GetPath()) for p in s.Traverse() if p.IsA(UsdPhysics.RevoluteJoint) or p.IsA(UsdPhysics.PrismaticJoint)])
print("catalog", (0.22, 0.028, 0.022))
