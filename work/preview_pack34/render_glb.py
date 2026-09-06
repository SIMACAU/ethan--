import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1 :]
glb = Path(argv[0])
out = Path(argv[1])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(glb))
pts = []
for obj in bpy.data.objects:
    if obj.type == "MESH":
        pts += [obj.matrix_world @ Vector(c) for c in obj.bound_box]
mins = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
maxs = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center = (mins + maxs) / 2
size = maxs - mins
print("bounds", tuple(round(float(size[i]), 4) for i in range(3)))
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
span = max(size.x, size.y, size.z, 0.04)
cam_data = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
cam.location = center + Vector((span * 1.4, -span * 2.1, span * 0.85))
cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = cam
scene.render.filepath = str(out)
bpy.ops.render.render(write_still=True)
print("wrote", out)
