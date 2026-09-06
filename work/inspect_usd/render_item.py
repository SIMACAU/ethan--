import bpy, math, sys
item = sys.argv[-2]
out = sys.argv[-1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.usd_import(filepath=rf"C:\Users\MACAU\Desktop\天池\output\submission\submission\{item}\{item}.usd")
pts = []
from mathutils import Vector
for o in bpy.data.objects:
    if o.type == "MESH":
        pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
ctr = (mn + mx) / 2
diag = (mx - mn).length
cam_data = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_data)
bpy.context.scene.collection.objects.link(cam)
cam.location = ctr + Vector((-0.9, -1.2, 0.55)) * diag * 0.9
direction = ctr - cam.location
cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = cam
sun_data = bpy.data.lights.new("sun", type="SUN")
sun = bpy.data.objects.new("sun", sun_data)
sun_data.energy = 3.0
bpy.context.scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(50), 0, math.radians(30))
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 640
sc.render.resolution_y = 480
sc.render.filepath = out
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.9, 1)
bpy.ops.render.render(write_still=True)
