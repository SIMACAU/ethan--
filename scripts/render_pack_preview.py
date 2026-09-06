"""Render a 3/4 view of each USD so the current pack can be inspected visually."""

from __future__ import annotations

from math import radians
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
USD_ROOT = ROOT / "output" / "submission" / "submission"
OUT = ROOT / "work" / "preview_pack28"


def clear() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.cameras, bpy.data.lights, bpy.data.objects):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def world_bounds(objects) -> tuple[Vector, Vector]:
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            mins.x, mins.y, mins.z = min(mins.x, point.x), min(mins.y, point.y), min(mins.z, point.z)
            maxs.x, maxs.y, maxs.z = max(maxs.x, point.x), max(maxs.y, point.y), max(maxs.z, point.z)
    return mins, maxs


def render_item(item_id: str) -> None:
    usd = USD_ROOT / item_id / f"{item_id}.usd"
    if not usd.exists():
        print("missing", item_id)
        return
    clear()
    bpy.ops.wm.usd_import(filepath=str(usd))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        print("no mesh", item_id)
        return
    mins, maxs = world_bounds(meshes)
    center = (mins + maxs) / 2
    size = maxs - mins
    span = max(size.x, size.y, size.z, 0.05)
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 50
    cam_data.clip_end = 50
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    offset = Vector((span * 1.55, -span * 2.05, span * 1.15))
    cam.location = center + offset
    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    light_data = bpy.data.lights.new("Key", "SUN")
    light_data.energy = 3.0
    light = bpy.data.objects.new("Key", light_data)
    light.rotation_euler = (radians(45), radians(15), radians(30))
    bpy.context.scene.collection.objects.link(light)
    fill = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", "SUN"))
    fill.data.energy = 1.2
    fill.rotation_euler = (radians(20), radians(-25), radians(-40))
    bpy.context.scene.collection.objects.link(fill)
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.82, 0.84, 0.86, 1.0)
        bg.inputs[1].default_value = 1.0
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    scene.render.filepath = str(OUT / f"{item_id}.jpg")
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 85
    scene.render.film_transparent = False
    bpy.ops.render.render(write_still=True)
    print("rendered", item_id, "span", round(span, 3))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.display.shading.light = "STUDIO"
    bpy.context.scene.display.shading.color_type = "TEXTURE"
    for index in range(1, 35):
        render_item(f"item_{index:03d}")


if __name__ == "__main__":
    main()
