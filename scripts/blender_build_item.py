"""Build a simulation-ready USD from category priors and optional photogrammetry."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector
from pxr import Gf, Usd, UsdGeom, UsdPhysics, UsdShade

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from asset_catalog import CATALOG  # noqa: E402


MATERIAL_PRESETS = {
    "plastic": (0.42, 0.0),
    "painted_wood": (0.52, 0.0),
    "wood": (0.62, 0.0),
    "metal": (0.28, 0.82),
    "fabric": (0.86, 0.0),
    "ceramic": (0.34, 0.0),
    "cardboard": (0.74, 0.0),
    "paper": (0.82, 0.0),
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("item_id")
    parser.add_argument("output_usd", type=Path)
    parser.add_argument("--glb", type=Path, default=None)
    parser.add_argument("--texture", type=Path, default=None)
    parsed = parser.parse_args(argv)
    if parsed.glb is not None:
        parsed.glb = parsed.glb.resolve()
    if parsed.texture is not None:
        parsed.texture = parsed.texture.resolve()
    parsed.output_usd = parsed.output_usd.resolve()
    return parsed


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.objects):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def make_material(name: str, color: tuple[float, float, float], kind: str, texture: Path | None = None):
    roughness, metallic = MATERIAL_PRESETS.get(kind, (0.5, 0.0))
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic
    if texture and texture.exists():
        image = bpy.data.images.load(str(texture.resolve()))
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.location = (-400, 200)
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def assign(obj: bpy.types.Object, material) -> None:
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)


def finish_mesh(obj: bpy.types.Object, parent: bpy.types.Object | None, material) -> bpy.types.Object:
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    if parent is not None:
        world = obj.matrix_world.copy()
        obj.parent = parent
        obj.matrix_world = world
    assign(obj, material)
    obj.select_set(False)
    return obj


def add_extruded_loop(name: str, points_xz, thickness: float, location, parent, material) -> bpy.types.Object:
    half = thickness / 2.0
    verts = [(x, -half, z) for x, z in points_xz] + [(x, half, z) for x, z in points_xz]
    count = len(points_xz)
    faces = []
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, nxt + count, index + count))
    faces.append(tuple(range(count - 1, -1, -1)))
    faces.append(tuple(range(count, count * 2)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return finish_mesh(obj, parent, material)


def add_cube(name: str, dims, location, parent, material, rotation=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    obj.dimensions = Vector(dims)
    return finish_mesh(obj, parent, material)


def add_cylinder(name: str, radius: float, depth: float, location, parent, material, rotation=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=location, rotation=rotation, vertices=32)
    obj = bpy.context.active_object
    obj.name = name
    return finish_mesh(obj, parent, material)


def add_cone(
    name: str,
    radius1: float,
    radius2: float,
    depth: float,
    location,
    parent,
    material,
    rotation=(0.0, 0.0, 0.0),
    scale=(1.0, 1.0, 1.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cone_add(
        radius1=radius1,
        radius2=radius2,
        depth=depth,
        location=location,
        rotation=rotation,
        vertices=32,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = Vector(scale)
    return finish_mesh(obj, parent, material)


def add_uv_sphere(name: str, radius: float, location, parent, material) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=24, ring_count=16)
    obj = bpy.context.active_object
    obj.name = name
    return finish_mesh(obj, parent, material)


def add_open_bowl(
    name: str,
    radius: float,
    height: float,
    wall: float,
    location,
    parent,
    material,
    style: str = "bowl",
) -> bpy.types.Object:
    """Create a closed lathed shell with a visible inner cavity."""
    segments = 48
    inner_radius = max(radius - wall, radius * 0.75)
    if style == "mug":
        profile = [
            (0.0, 0.0),
            (radius * 0.62, height * 0.04),
            (radius * 0.92, height * 0.16),
            (radius, height),
            (inner_radius, height),
            (inner_radius * 0.94, height * 0.20),
            (inner_radius * 0.62, height * 0.08),
            (0.0, wall),
        ]
    elif style == "wok":
        profile = [
            (0.0, 0.0),
            (radius * 0.42, height * 0.10),
            (radius * 0.78, height * 0.36),
            (radius, height),
            (inner_radius, height),
            (inner_radius * 0.74, height * 0.34),
            (inner_radius * 0.36, height * 0.12),
            (0.0, wall),
        ]
    elif style == "tube":
        profile = [
            (0.0, 0.0),
            (radius * 0.92, wall),
            (radius, height),
            (inner_radius, height),
            (inner_radius, wall * 2),
            (0.0, wall),
        ]
    else:
        profile = [
            (0.0, 0.0),
            (radius * 0.38, height * 0.02),
            (radius * 0.72, height * 0.16),
            (radius * 0.94, height * 0.54),
            (radius, height),
            (inner_radius, height),
            (inner_radius * 0.91, height * 0.58),
            (inner_radius * 0.62, height * 0.26),
            (0.0, wall),
        ]
    vertices: list[tuple[float, float, float]] = []
    rings: list[list[int]] = []
    for ring_radius, ring_z in profile:
        if ring_radius == 0.0:
            rings.append([len(vertices)])
            vertices.append((0.0, 0.0, ring_z))
            continue
        ring: list[int] = []
        for index in range(segments):
            angle = 2.0 * math.pi * index / segments
            ring.append(len(vertices))
            vertices.append(
                (
                    ring_radius * math.cos(angle),
                    ring_radius * math.sin(angle),
                    ring_z,
                )
            )
        rings.append(ring)

    faces: list[tuple[int, ...]] = []
    for current, following in zip(rings, rings[1:]):
        if len(current) == 1:
            for index in range(segments):
                faces.append((current[0], following[(index + 1) % segments], following[index]))
        elif len(following) == 1:
            for index in range(segments):
                faces.append((current[index], current[(index + 1) % segments], following[0]))
        else:
            for index in range(segments):
                next_index = (index + 1) % segments
                faces.append(
                    (
                        current[index],
                        current[next_index],
                        following[next_index],
                        following[index],
                    )
                )

    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        polygon_uvs: list[float] = []
        for loop_index in polygon.loop_indices:
            vertex = mesh.vertices[mesh.loops[loop_index].vertex_index]
            polygon_uvs.append(
                (math.atan2(vertex.co.y, vertex.co.x) / (2.0 * math.pi) + 0.5) % 1.0
            )
        crosses_seam = max(polygon_uvs) - min(polygon_uvs) > 0.5
        for loop_index, u_value in zip(polygon.loop_indices, polygon_uvs):
            vertex = mesh.vertices[mesh.loops[loop_index].vertex_index]
            if crosses_seam and u_value < 0.5:
                u_value += 1.0
            uv_layer.data[loop_index].uv = (u_value, vertex.co.z / height)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    return finish_mesh(obj, parent, material)


def add_torus(name: str, major: float, minor: float, location, parent, material, rotation=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        location=location,
        rotation=rotation,
        major_radius=major,
        minor_radius=minor,
    )
    obj = bpy.context.active_object
    obj.name = name
    return finish_mesh(obj, parent, material)


def add_plane(name: str, size: float, location, parent, material, rotation=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_plane_add(size=size, location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    return finish_mesh(obj, parent, material)


def add_empty(name: str, parent: bpy.types.Object | None, location=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    if parent is not None:
        world = obj.matrix_world.copy()
        obj.parent = parent
        obj.matrix_world = world
    return obj


def add_shell_box(parent: bpy.types.Object, x: float, y: float, z: float, wall: float, material, open_front: bool = False, open_top: bool = False) -> None:
    """Axis-aligned hollow box whose panels share faces but do not overlap volumes."""
    inner_h = max(z - wall, wall)
    add_cube("shell_bottom", (x, y, wall), (0, 0, wall / 2), parent, material)
    if not open_top:
        add_cube("shell_top", (x, y, wall), (0, 0, z - wall / 2), parent, material)
        wall_h = max(z - 2 * wall, wall)
        wall_z = z / 2
    else:
        wall_h = inner_h
        wall_z = wall + inner_h / 2
    add_cube("shell_left", (wall, y, wall_h), (-x / 2 + wall / 2, 0, wall_z), parent, material)
    add_cube("shell_right", (wall, y, wall_h), (x / 2 - wall / 2, 0, wall_z), parent, material)
    span_x = max(x - 2 * wall, wall)
    add_cube("shell_back", (span_x, wall, wall_h), (0, y / 2 - wall / 2, wall_z), parent, material)
    if not open_front:
        add_cube("shell_front", (span_x, wall, wall_h), (0, -y / 2 + wall / 2, wall_z), parent, material)


def add_four_legs(parent, x: float, y: float, height: float, material, inset: float = 0.05, radius: float = 0.014, square: bool = False) -> None:
    for index, (sx, sy) in enumerate(((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0))):
        loc = (sx * (x / 2 - inset), sy * (y / 2 - inset), height / 2)
        if square:
            add_cube(f"leg_{index + 1}", (radius * 2, radius * 2, height), loc, parent, material)
        else:
            add_cylinder(f"leg_{index + 1}", radius, height, loc, parent, material)


def build_geometry(spec: dict, root: bpy.types.Object, body_mat, accent_mat, dark_mat, glass_mat, chrome_mat) -> None:
    kind = spec["kind"]
    x, y, z = spec["size"]

    if kind == "cabinet_2door":
        white = make_material("CabinetWhite", (0.96, 0.96, 0.97), "painted_wood")
        add_cube("Body", (x, y, z), (0, 0, z / 2), root, white)
        for index, cz in enumerate((z * 0.22, z * 0.44, z * 0.66, z * 0.86)):
            add_cube(f"shelf_{index + 1}", (x * 0.90, y * 0.86, 0.012), (0, 0.004, cz), root, white)
        door_w = x * 0.475
        door_h = z * 0.90
        frame = 0.030
        door_left = add_cube("door_left", (door_w, 0.018, door_h), (-x * 0.245, -y / 2 + 0.009, z / 2), root, white)
        door_right = add_cube("door_right", (door_w, 0.018, door_h), (x * 0.245, -y / 2 + 0.009, z / 2), root, white)
        add_cube("glass_left", (max(door_w - 2 * frame, 0.08), 0.006, max(door_h - 2 * frame, 0.08)), (-x * 0.245, -y / 2 - 0.002, z / 2), door_left, glass_mat)
        add_cube("glass_right", (max(door_w - 2 * frame, 0.08), 0.006, max(door_h - 2 * frame, 0.08)), (x * 0.245, -y / 2 - 0.002, z / 2), door_right, glass_mat)
        add_cylinder("handle_left", 0.010, 0.014, (-0.028, -y / 2 - 0.012, z * 0.50), door_left, white, rotation=(math.pi / 2, 0, 0))
        add_cylinder("handle_right", 0.010, 0.014, (0.028, -y / 2 - 0.012, z * 0.50), door_right, white, rotation=(math.pi / 2, 0, 0))

    elif kind == "sideboard":
        white = make_material("SideboardWhite", (0.96, 0.96, 0.97), "painted_wood")
        wood = make_material("SideboardWood", (0.78, 0.64, 0.42), "wood")
        plinth = 0.055
        carcass_h = z - plinth - 0.028
        add_cube("Body", (x, y, carcass_h), (0, 0, plinth + carcass_h / 2), root, white)
        add_cube("top", (x * 1.01, y * 1.02, 0.028), (0, 0, z - 0.014), root, wood)
        add_four_legs(root, x * 0.94, y * 0.90, plinth, white, inset=0.03, radius=0.016, square=True)
        add_cube("leg_mid_f", (0.032, 0.032, plinth), (0, -y * 0.45 + 0.04, plinth / 2), root, white)
        add_cube("leg_mid_b", (0.032, 0.032, plinth), (0, y * 0.45 - 0.04, plinth / 2), root, white)
        door_w = x * 0.28
        door_h = carcass_h * 0.90
        door_z = plinth + carcass_h * 0.50
        door_left = add_cube("door_left", (door_w, 0.016, door_h), (-x * 0.34, -y / 2 + 0.008, door_z), root, white)
        door_right = add_cube("door_right", (door_w, 0.016, door_h), (x * 0.34, -y / 2 + 0.008, door_z), root, white)
        add_cube("glass_left", (door_w * 0.78, 0.006, door_h * 0.82), (-x * 0.34, -y / 2 - 0.002, door_z), door_left, glass_mat)
        add_cube("glass_right", (door_w * 0.78, 0.006, door_h * 0.82), (x * 0.34, -y / 2 - 0.002, door_z), door_right, glass_mat)
        add_cube("glass_shelf_l", (door_w * 0.86, y * 0.70, 0.008), (-x * 0.34, 0, plinth + door_h * 0.52), root, glass_mat)
        add_cube("glass_shelf_r", (door_w * 0.86, y * 0.70, 0.008), (x * 0.34, 0, plinth + door_h * 0.52), root, glass_mat)
        add_cube("drawer", (x * 0.32, y * 0.90, carcass_h * 0.42), (0, -0.006, plinth + carcass_h * 0.72), root, white)
        add_cube("drawer_2", (x * 0.32, y * 0.90, carcass_h * 0.42), (0, -0.006, plinth + carcass_h * 0.28), root, white)

    elif kind == "nightstand":
        # White cabinet: open upper niche + lower door. No catalog size change.
        white = make_material("NightstandWhite", (0.94, 0.94, 0.95), "painted_wood")
        wall = 0.018
        top_h = 0.028
        base_h = 0.040
        door_h = z * 0.42
        niche_h = max(z - top_h - base_h - door_h, 0.08)
        carcass_h = base_h + door_h
        add_cube("Body", (x, y, carcass_h), (0, 0, carcass_h / 2), root, white)
        add_cube("top", (x * 1.02, y * 1.02, top_h), (0, 0, z - top_h / 2), root, white)
        shelf_z = carcass_h
        add_cube("shelf", (x - 2 * wall, y - wall, 0.014), (0, wall * 0.15, shelf_z + 0.007), root, white)
        add_cube("side_l", (wall, y, niche_h), (-x / 2 + wall / 2, 0, shelf_z + niche_h / 2), root, white)
        add_cube("side_r", (wall, y, niche_h), (x / 2 - wall / 2, 0, shelf_z + niche_h / 2), root, white)
        add_cube("back", (x - 2 * wall, wall, niche_h), (0, y / 2 - wall / 2, shelf_z + niche_h / 2), root, white)
        door = add_cube(
            "door",
            (x * 0.90, 0.016, door_h * 0.88),
            (0, -y / 2 + 0.008, base_h + door_h * 0.50),
            root,
            white,
        )
        add_cylinder(
            "knob",
            0.010,
            0.014,
            (-x * 0.28, -y / 2 - 0.010, base_h + door_h * 0.50),
            door,
            chrome_mat,
            rotation=(math.pi / 2, 0, 0),
        )

    elif kind == "dresser_6":
        white = make_material("DresserWhite", (0.95, 0.94, 0.90), "painted_wood")
        brass = make_material("DresserBrass", (0.72, 0.55, 0.22), "metal")
        add_cube("Body", (x, y, z), (0, 0, z / 2), root, white)
        add_cube("top", (x * 1.02, y * 1.02, 0.020), (0, 0, z + 0.006), root, white)
        for index in range(6):
            row, col = divmod(index, 2)
            cx = (-0.24 if col == 0 else 0.24) * x
            cz = z * (0.18 + row * 0.28)
            drawer = add_cube(
                f"drawer_{index + 1}",
                (x * 0.44, y * 0.86, z * 0.14),
                (cx, -y * 0.02, cz),
                root,
                white,
            )
            add_cube(
                f"panel_{index + 1}",
                (x * 0.34, 0.006, z * 0.09),
                (cx, -y * 0.45 - 0.003, cz),
                drawer,
                white,
            )
            add_torus(
                f"knob_{index + 1}",
                0.018,
                0.006,
                (cx, -y * 0.45 - 0.020, cz + z * 0.038),
                drawer,
                brass,
                rotation=(math.pi / 2, 0, 0),
            )

    elif kind == "office_chair":
        # White plastic shell, black ribbed cushion, white star base and casters.
        shell = make_material("ChairWhite", (0.95, 0.95, 0.96), "plastic")
        cushion_mat = make_material("ChairCushion", (0.11, 0.11, 0.12), "fabric")
        seat_h = z * 0.50
        add_cube("Body", (x * 0.52, y * 0.52, 0.040), (0, 0.02, seat_h), root, shell)
        add_cube("cushion", (x * 0.46, y * 0.44, 0.048), (0, 0.03, seat_h + 0.044), root, cushion_mat)
        for index in range(4):
            add_cube(
                f"rib_{index + 1}",
                (0.007, y * 0.38, 0.010),
                ((index - 1.5) * 0.075, 0.03, seat_h + 0.070),
                root,
                dark_mat,
            )
        add_cube("back", (x * 0.50, 0.042, z * 0.36), (0, -y * 0.22, seat_h + z * 0.28), root, shell)
        add_cube("back_left", (0.055, 0.042, z * 0.16), (-x * 0.18, -y * 0.22, seat_h + z * 0.10), root, shell)
        add_cube("back_right", (0.055, 0.042, z * 0.16), (x * 0.18, -y * 0.22, seat_h + z * 0.10), root, shell)
        pole_h = seat_h - 0.08
        add_cylinder("swivel", 0.026, pole_h, (0, 0, pole_h / 2 + 0.055), root, shell)
        for angle in range(5):
            rad = math.radians(angle * 72 + 90)
            add_cube(
                f"leg_{angle}",
                (0.042, 0.24, 0.032),
                (0.14 * math.cos(rad), 0.14 * math.sin(rad), 0.068),
                root,
                shell,
                rotation=(0, 0, rad - math.pi / 2),
            )
            add_cylinder(
                f"caster_{angle}",
                0.024,
                0.022,
                (0.26 * math.cos(rad), 0.26 * math.sin(rad), 0.024),
                root,
                shell,
                rotation=(math.pi / 2, 0, rad),
            )

    elif kind == "floor_lamp":
        add_cylinder("Body", 0.13, 0.022, (0, 0, 0.011), root, accent_mat)
        add_cylinder("base_2", 0.09, 0.028, (0, 0, 0.036), root, accent_mat)
        add_cylinder("base_3", 0.055, 0.030, (0, 0, 0.064), root, accent_mat)
        pole_h = z - 0.40
        add_cylinder("pole", 0.011, pole_h, (0, 0, 0.08 + pole_h / 2), root, accent_mat)
        add_cylinder("shade", 0.16, 0.22, (0, 0, z - 0.14), root, body_mat)
        add_cylinder("switch", 0.016, 0.010, (0.12, 0, 0.010), root, body_mat)

    elif kind == "l_sofa":
        # Video is a left-arm two-seater, not a chaise L.
        leg_h = 0.16
        add_cube("Body", (x * 0.96, y * 0.78, 0.16), (0.02 * x, 0.02, leg_h + 0.08), root, body_mat)
        add_cube("arm_left", (0.16, y * 0.78, 0.38), (-x * 0.40, 0.02, leg_h + 0.35), root, body_mat)
        add_cube("back_1", (x * 0.40, 0.14, 0.36), (-x * 0.12, -y * 0.30, leg_h + 0.42), root, body_mat)
        add_cube("back_2", (x * 0.40, 0.14, 0.36), (x * 0.28, -y * 0.30, leg_h + 0.42), root, body_mat)
        add_four_legs(root, x * 0.90, y * 0.70, leg_h, dark_mat, inset=0.06, radius=0.016)

    elif kind == "lounge_chair":
        leg_h = 0.18
        add_cube("Body", (x * 0.96, y * 0.78, 0.16), (0, 0.02, leg_h + 0.08), root, body_mat)
        add_cube("back", (x * 0.96, 0.12, 0.38), (0, -y * 0.32, leg_h + 0.38), root, body_mat)
        add_four_legs(root, x * 0.88, y * 0.70, leg_h, dark_mat, inset=0.04, radius=0.014)

    elif kind == "ottoman":
        beige = make_material("OttomanBeige", (0.88, 0.84, 0.76), "fabric")
        ring = make_material("OttomanRing", (0.94, 0.94, 0.95), "plastic")
        leg_h = 0.14
        add_cube("Body", (x, y, z * 0.62), (0, 0, leg_h + z * 0.31), root, beige)
        add_four_legs(root, x, y, leg_h, dark_mat, inset=0.05, radius=0.012)
        for index, (sx, sy) in enumerate(((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0))):
            add_cylinder(
                f"ring_{index + 1}",
                0.014,
                0.008,
                (sx * (x / 2 - 0.05), sy * (y / 2 - 0.05), 0.018),
                root,
                ring,
            )

    elif kind == "side_table":
        top_h = 0.12
        add_cube("Body", (x, y, top_h), (0, 0, z - top_h / 2), root, body_mat)
        add_four_legs(root, x, y, z - top_h, dark_mat, inset=0.04, radius=0.015, square=True)

    elif kind == "knife":
        # Cream sheathed paring knife: round handle + rounded plastic sheath.
        cream = make_material("KnifeCream", (0.90, 0.86, 0.78), "plastic")
        hz = z * 0.46
        handle_l = x * 0.32
        sheath_l = x * 0.58
        handle_x = -x / 2 + hz + handle_l / 2
        add_cylinder(
            "handle",
            hz,
            handle_l,
            (handle_x, 0.0, hz),
            root,
            cream,
            rotation=(0.0, math.pi / 2, 0.0),
        )
        add_uv_sphere("pommel", hz, (handle_x - handle_l / 2, 0.0, hz), root, cream)
        h = z * 0.92
        add_extruded_loop(
            "Body",
            [
                (0.00, h * 0.16),
                (sheath_l * 0.48, h * 0.12),
                (sheath_l * 0.84, h * 0.24),
                (sheath_l * 0.99, h * 0.50),
                (sheath_l * 0.84, h * 0.78),
                (sheath_l * 0.42, h * 0.94),
                (0.00, h * 0.84),
            ],
            y * 0.78,
            (handle_x + handle_l / 2 - 0.004, 0.0, 0.0),
            root,
            cream,
        )
        add_cone(
            "slot",
            0.0020,
            0.0020,
            y * 0.86,
            (handle_x + handle_l / 2 + sheath_l * 0.52, 0.0, h * 0.50),
            root,
            dark_mat,
            rotation=(math.pi / 2, 0.0, 0.0),
            scale=(2.8, 1.0, 1.0),
        )

    elif kind == "toaster":
        body = add_empty("Body", root)
        wall = 0.006
        add_shell_box(body, x, y, z, wall, body_mat, open_top=True)
        usable_x = x - 2 * wall
        divider = 0.008
        slot_w = (usable_x - 3 * divider) / 4
        inner_y = y - 2 * wall
        inner_h = z - wall
        start = -x / 2 + wall + slot_w / 2
        for index in range(3):
            dx = start + slot_w / 2 + divider / 2 + index * (slot_w + divider)
            add_cube(f"divider_{index + 1}", (divider, inner_y, inner_h), (dx, 0, wall + inner_h / 2), body, body_mat)
        front = -y / 2
        add_cube("lever_left", (0.014, 0.012, 0.078), (-0.048, front - 0.007, z * 0.58), root, chrome_mat)
        add_cube("lever_right", (0.014, 0.012, 0.078), (0.048, front - 0.007, z * 0.58), root, chrome_mat)
        add_cylinder("knob_left", 0.013, 0.016, (-0.11, front - 0.008, 0.038), root, accent_mat, rotation=(math.pi / 2, 0, 0))
        add_cylinder("knob_right", 0.013, 0.016, (0.11, front - 0.008, 0.038), root, accent_mat, rotation=(math.pi / 2, 0, 0))
        for index in range(8):
            col, row = divmod(index, 4)
            add_cube(
                f"button_{index + 1}",
                (0.012, 0.006, 0.010),
                (-0.014 + col * 0.028, front - 0.004, 0.055 + row * 0.018),
                root,
                dark_mat,
            )
        add_cylinder("window_left", 0.018, 0.005, (-0.09, front - 0.002, 0.095), body, glass_mat, rotation=(math.pi / 2, 0, 0))
        add_cylinder("window_right", 0.018, 0.005, (0.09, front - 0.002, 0.095), body, glass_mat, rotation=(math.pi / 2, 0, 0))
        add_cube("chrome_top", (x * 0.98, y * 0.98, 0.003), (0, 0, z - 0.0015), body, chrome_mat)
        add_cube("chrome_base", (x * 1.02, y * 1.02, 0.008), (0, 0, 0.008), body, chrome_mat)
        add_cube("badge", (0.04, 0.004, 0.012), (0, front - 0.003, z * 0.88), body, chrome_mat)
        for index, px in enumerate((-1.0, 1.0)):
            for py in (-1.0, 1.0):
                add_cylinder(
                    f"foot_{index}_{int(py)}",
                    0.009,
                    0.012,
                    (px * (x / 2 - 0.02), py * (y / 2 - 0.02), 0.006),
                    body,
                    dark_mat,
                )

    elif kind == "microwave":
        # White Midea-style microwave; do not wrap the room photo onto the body.
        white = make_material("MicrowaveWhite", (0.93, 0.93, 0.94), "plastic")
        body = add_empty("Body", root)
        add_shell_box(body, x, y, z, 0.012, white, open_front=True)
        door = add_cube("door", (x * 0.68, 0.02, z), (-x * 0.16, -y / 2 + 0.01, z / 2), root, white)
        add_cube("window_frame", (x * 0.50, 0.004, z * 0.62), (-x * 0.16, -y / 2 - 0.002, z / 2), door, accent_mat)
        add_cube("door_window", (x * 0.42, 0.006, z * 0.52), (-x * 0.16, -y / 2 - 0.006, z / 2), door, glass_mat)
        add_cube("door_handle", (0.018, 0.022, z * 0.70), (x * 0.14, -y / 2 - 0.018, z / 2), door, chrome_mat)
        add_cube("panel", (x * 0.32, 0.02, z), (x * 0.34, -y / 2 + 0.01, z / 2), root, white)
        add_cube("display", (x * 0.18, 0.006, z * 0.22), (x * 0.34, -y / 2 - 0.004, z * 0.78), root, dark_mat)
        for index in range(5):
            add_cylinder(
                f"button_{index + 1}",
                0.012,
                0.010,
                (x * 0.34, -y / 2 - 0.006, z * 0.62 - index * 0.038),
                root,
                chrome_mat,
                rotation=(math.pi / 2, 0, 0),
            )
        add_cylinder("dial", 0.028, 0.016, (x * 0.34, -y / 2 - 0.008, z * 0.18), root, chrome_mat, rotation=(math.pi / 2, 0, 0))
        add_cylinder("turntable", min(x, y) * 0.34, 0.008, (0, 0, 0.018), body, glass_mat)

    elif kind == "rice_cooker":
        add_cube("Body", (x * 0.92, y * 0.92, z * 0.62), (0, 0, z * 0.31), root, body_mat)
        lid = add_cube("lid", (x * 0.92, y * 0.92, z * 0.22), (0, 0, z * 0.75), root, body_mat)
        add_cylinder("display", 0.05, 0.006, (0, 0, z * 0.87), lid, dark_mat)
        add_cube("button", (0.09, 0.014, 0.032), (0, -y * 0.47, z * 0.58), root, body_mat)

    elif kind == "air_fryer":
        add_cube("Body", (x, y, z * 0.46), (0, 0, z * 0.77), root, body_mat)
        basket = add_cube("basket", (x * 0.96, y * 0.94, z * 0.50), (0, -0.01, z * 0.27), root, body_mat)
        add_cube("handle", (0.055, 0.045, z * 0.32), (0, -y / 2 - 0.018, z * 0.27), basket, body_mat)
        add_cube("window_l", (x * 0.22, 0.008, z * 0.22), (-x * 0.28, -y / 2 - 0.006, z * 0.27), basket, glass_mat)
        add_cube("window_r", (x * 0.22, 0.008, z * 0.22), (x * 0.28, -y / 2 - 0.006, z * 0.27), basket, glass_mat)
        add_cylinder("knob_time", 0.022, 0.018, (0, -y / 2 - 0.010, z * 0.88), root, body_mat, rotation=(math.pi / 2, 0, 0))
        add_cylinder("knob_temp", 0.022, 0.018, (0, -y / 2 - 0.010, z * 0.70), root, body_mat, rotation=(math.pi / 2, 0, 0))

    elif kind == "kettle":
        # All-white cylindrical kettle with a rectangular D-handle; lid stays hinged.
        white = make_material("KettleWhite", (0.93, 0.93, 0.94), "plastic")
        add_cylinder("Body", x / 2 * 0.72, z * 0.78, (0, 0, z * 0.40), root, white)
        add_cylinder("lid", x / 2 * 0.68, 0.016, (0, 0, z * 0.80), root, white)
        add_cube(
            "spout",
            (0.040, 0.028, 0.032),
            (-x * 0.32, 0, z * 0.70),
            root,
            white,
            rotation=(0, math.radians(-28), 0),
        )
        body_r = x / 2 * 0.72
        add_cube("handle", (0.016, 0.022, z * 0.36), (body_r + 0.058, 0, z * 0.48), root, white)
        add_cube("handle_top", (0.058, 0.022, 0.016), (body_r + 0.029, 0, z * 0.66), root, white)
        add_cube("handle_bot", (0.058, 0.022, 0.016), (body_r + 0.029, 0, z * 0.30), root, white)

    elif kind == "laptop":
        # Closed ThinkPad: matte black clamshell, no room-photo texture wrap.
        dark = make_material("LaptopDark", (0.12, 0.12, 0.13), "plastic")
        base = add_cube("Body", (x, y, 0.011), (0, 0, 0.0055), root, dark)
        add_cube("screen", (x, y, 0.009), (0, 0, 0.016), root, dark)
        add_cube("logo", (0.036, 0.010, 0.001), (0, -y * 0.28, 0.021), root, chrome_mat)

    elif kind == "mouse":
        pink = make_material("MousePink", (0.78, 0.58, 0.62), "plastic")
        add_uv_sphere("Body", 0.032, (0, 0, 0.018), root, pink)
        bpy.context.view_layer.objects.active = bpy.data.objects["Body"]
        bpy.data.objects["Body"].scale = (1.55, 1.0, 0.55)
        finish_mesh(bpy.data.objects["Body"], root, pink)
        add_cylinder("wheel", 0.007, 0.014, (0, 0.010, 0.030), root, dark_mat, rotation=(math.pi / 2, 0, 0))
        add_cube("dpi", (0.010, 0.006, 0.004), (0, -0.004, 0.034), root, dark_mat)
        add_cube("usbc", (0.008, 0.006, 0.004), (0, y * 0.42, 0.008), root, dark_mat)

    elif kind == "monitor":
        add_cube("stand_l", (0.045, 0.24, 0.018), (-0.09, 0.05, 0.01), root, dark_mat, rotation=(0, 0, math.radians(28)))
        add_cube("stand_r", (0.045, 0.24, 0.018), (0.09, 0.05, 0.01), root, dark_mat, rotation=(0, 0, math.radians(-28)))
        add_cube("neck", (0.04, 0.04, 0.16), (0, 0, 0.12), root, dark_mat)
        add_torus("red_ring", 0.032, 0.007, (0, 0.02, 0.055), root, accent_mat, rotation=(math.pi / 2, 0, 0))
        add_cube("Body", (x, 0.05, z * 0.72), (0, 0, 0.30), root, body_mat)
        add_cube("tilt", (x * 0.98, 0.018, z * 0.68), (0, -0.028, 0.30), root, dark_mat)

    elif kind == "tissue_box":
        add_cube("Body", (x, y, z), (0, 0, z / 2), root, body_mat)
        add_cube("hang_tab", (0.04, y * 0.55, 0.08), (-x / 2 - 0.018, 0, z * 0.62), root, body_mat)
        add_cube("slot", (x * 0.70, y * 0.18, 0.006), (0, 0, 0.004), root, accent_mat)

    elif kind == "toilet_paper":
        add_cube("Body", (x, y, z), (0, 0, z / 2), root, body_mat)
        for index in range(12):
            row, col = divmod(index, 4)
            add_cylinder(
                f"roll_{index + 1}",
                min(x, y) * 0.10,
                z * 0.28,
                ((col - 1.5) * x * 0.22, (row - 1) * y * 0.28, z * 0.22 + row * z * 0.26),
                root,
                accent_mat,
                rotation=(math.pi / 2, 0, 0),
            )

    elif kind == "mug":
        add_open_bowl(
            "Body",
            radius=x / 2,
            height=z,
            wall=0.004,
            location=(0, 0, 0),
            parent=root,
            material=body_mat,
            style="mug",
        )
        add_torus("handle_top", 0.022, 0.007, (x * 0.48, 0, z * 0.62), root, accent_mat, rotation=(math.pi / 2, 0, 0))
        add_torus("handle_bot", 0.022, 0.007, (x * 0.48, 0, z * 0.38), root, accent_mat, rotation=(math.pi / 2, 0, 0))

    elif kind == "trash_can":
        add_cylinder("Body", x / 2 * 0.88, z * 0.88, (0, 0, z * 0.44), root, body_mat)
        add_torus("rim", x / 2 * 0.90, 0.012, (0, 0, z * 0.90), root, body_mat)
        add_cylinder("inner", x / 2 * 0.72, 0.01, (0, 0, z * 0.86), root, dark_mat)

    elif kind == "chip_bag":
        add_cube("Body", (x, y, z * 0.82), (0, 0, z * 0.41), root, body_mat)
        add_cube("seal", (x * 0.92, y * 0.55, 0.012), (0, 0, z * 0.92), root, body_mat)

    elif kind == "chip_can":
        add_open_bowl(
            "Body",
            radius=x / 2,
            height=z * 0.90,
            wall=0.003,
            location=(0, 0, 0),
            parent=root,
            material=body_mat,
            style="tube",
        )
        add_cylinder("lid", x / 2 * 1.02, 0.02, (0, 0, z * 0.96), root, accent_mat)

    elif kind == "seasoning_box":
        add_cube("Body", (x, y, z * 0.82), (0, 0, z * 0.41), root, body_mat)
        add_cube("flap", (x, y, 0.012), (0, 0, z * 0.90), root, body_mat)
        add_cube("photo", (x * 0.92, y * 0.02, z * 0.42), (0, -y / 2 - 0.002, z * 0.58), root, dark_mat)

    elif kind == "spatula":
        add_cube("Body", (x * 0.40, y * 1.35, z * 0.28), (x * 0.22, 0, z / 2), root, body_mat)
        add_cylinder("handle", 0.011, x * 0.58, (-x * 0.22, 0, z / 2), root, body_mat, rotation=(0, math.pi / 2, 0))
        add_cylinder("hole", 0.006, z * 1.5, (-x * 0.44, 0, z / 2), root, dark_mat)

    elif kind == "bowl":
        add_open_bowl(
            "Body",
            radius=x / 2,
            height=z,
            wall=0.006,
            location=(0, 0, 0),
            parent=root,
            material=body_mat,
        )

    elif kind == "plate":
        add_cylinder("Body", x / 2 * 0.72, z, (0, -y * 0.06, z / 2), root, body_mat)
        add_cylinder("ear_left", x / 2 * 0.22, z * 0.85, (-x * 0.28, y * 0.28, z / 2), root, body_mat)
        add_cylinder("ear_right", x / 2 * 0.22, z * 0.85, (x * 0.28, y * 0.28, z / 2), root, body_mat)

    elif kind == "cutting_board":
        add_cube("Body", (x * 0.78, y, z), (x * 0.08, 0, z / 2), root, body_mat)
        add_cube("handle", (x * 0.22, y * 0.42, z), (-x * 0.40, 0, z / 2), root, body_mat)
        add_cylinder("hole", 0.008, z * 1.2, (-x * 0.42, 0, z / 2), root, dark_mat)

    elif kind == "wok":
        add_cylinder("Body", x / 2, z * 0.48, (0, 0, z * 0.24), root, body_mat)
        add_cylinder("handle", 0.014, 0.18, (x * 0.58, 0, z * 0.22), root, accent_mat, rotation=(0, math.pi / 2, 0))
        add_torus("helper", 0.028, 0.008, (-x * 0.42, 0, z * 0.28), root, accent_mat, rotation=(math.pi / 2, 0, 0))
        add_cylinder("lid", x / 2 * 0.88, 0.012, (0, 0, z * 0.55), root, glass_mat)
        add_cylinder("lid_knob", 0.016, 0.028, (0, 0, z * 0.62), root, dark_mat)

    elif kind == "juice_box":
        add_cube("Body", (x, y, z * 0.78), (0, 0, z * 0.39), root, body_mat)
        add_cube("flap_front", (x, 0.01, z * 0.22), (0, -y / 2, z * 0.90), root, body_mat)
        add_torus("handle", 0.032, 0.006, (0, 0, z * 0.86), root, glass_mat, rotation=(math.pi / 2, 0, 0))
        for index in range(10):
            row, col = divmod(index, 5)
            add_cylinder(
                f"bottle_{index + 1}",
                0.014,
                0.15,
                ((col - 2) * 0.055, (row - 0.5) * 0.055, z * 0.40),
                root,
                dark_mat,
            )

    elif kind == "pantry_scene":
        # White room, grey tile floor, kitchenette at back, glass partition with door at front.
        add_cube("Floor", (x, y, 0.04), (0, 0, 0.02), root, accent_mat)
        add_cube("WallBack", (x, 0.06, z), (0, y / 2, z / 2), root, body_mat)
        add_cube("WallLeft", (0.06, y, z), (-x / 2, 0, z / 2), root, body_mat)
        add_cube("WallRight", (0.06, y, z), (x / 2, 0, z / 2), root, body_mat)
        add_cube("Counter", (1.8, 0.62, 0.84), (-1.1, y / 2 - 0.37, 0.44), root, chrome_mat)
        add_cube("counter_top", (1.84, 0.66, 0.04), (-1.1, y / 2 - 0.37, 0.88), root, body_mat)
        add_cylinder("faucet", 0.015, 0.24, (-1.1, y / 2 - 0.20, 1.02), root, chrome_mat)
        add_cube("drawer", (0.46, 0.56, 0.15), (-1.5, y / 2 - 0.43, 0.70), root, chrome_mat)
        add_cube("Body", (0.85, 0.45, 0.84), (1.0, y / 2 - 0.28, 0.44), root, body_mat)
        door = add_cube("cabinet_door", (0.40, 0.02, 0.76), (0.79, y / 2 - 0.515, 0.46), root, body_mat)
        add_cube("cabinet_door_r", (0.40, 0.02, 0.76), (1.21, y / 2 - 0.515, 0.46), root, body_mat)
        add_cube("door_handle", (0.014, 0.014, 0.30), (1.02, y / 2 - 0.535, 0.50), door, dark_mat)
        add_cylinder("lock", 0.008, 0.012, (1.02, y / 2 - 0.530, 0.62), door, chrome_mat, rotation=(math.pi / 2, 0, 0))
        add_cube("key", (0.004, 0.018, 0.028), (1.02, y / 2 - 0.548, 0.60), door, dark_mat)
        add_cube("table_top", (1.5, 0.6, 0.04), (1.3, -y / 2 + 0.55, 0.74), root, body_mat)
        for index, (px, py) in enumerate(((-0.68, -0.24), (0.68, -0.24), (-0.68, 0.24), (0.68, 0.24))):
            add_cube(
                f"table_leg_{index + 1}",
                (0.045, 0.045, 0.72),
                (1.3 + px, -y / 2 + 0.55 + py, 0.36),
                root,
                body_mat,
            )
        front = -y / 2 + 0.04
        add_cube("glass_wall_left", (1.9, 0.03, z - 0.10), (-1.15, front, (z - 0.10) / 2), root, glass_mat)
        add_cube("glass_wall_right", (1.4, 0.03, z - 0.10), (1.4, front, (z - 0.10) / 2), root, glass_mat)
        gdoor = add_cube("glass_door", (0.88, 0.03, z - 0.14), (0.25, front + 0.03, (z - 0.14) / 2), root, glass_mat)
        add_cube("glass_door_handle", (0.02, 0.02, 0.60), (0.60, front + 0.06, 1.10), gdoor, chrome_mat)
        for index, px in enumerate((-2.1, -0.20, 0.70, 2.1)):
            add_cube(f"frame_post_{index + 1}", (0.06, 0.06, z), (px, front, z / 2), root, dark_mat)
        add_cube("frame_top", (x, 0.06, 0.06), (0, front, z - 0.03), root, dark_mat)
        add_cube("brace", (0.08, 0.08, 2.2), (0.4, y / 2 - 0.12, 1.2), root, body_mat, rotation=(0, math.radians(38), 0))
        add_cube("ceiling_light", (0.6, 0.4, 0.04), (0, 0, z - 0.04), root, chrome_mat)
        add_cube("bin", (0.28, 0.22, 0.42), (-1.4, 0.2, 0.21), root, dark_mat)

    elif kind == "office_scene":
        # Wood floor, white walls, window with roller blind, oak cabinet with glass
        # upper doors, desk with drawer, hinged entry door on the left wall.
        add_cube("Floor", (x, y, 0.04), (0, 0, 0.02), root, body_mat)
        add_cube("WallBack", (x, 0.06, z), (0, y / 2, z / 2), root, accent_mat)
        add_cube("WallLeft", (0.06, y, z), (-x / 2, 0, z / 2), root, accent_mat)
        add_cube("window_frame", (1.7, 0.08, 1.7), (1.6, y / 2 - 0.02, 1.7), root, dark_mat)
        add_cube("window", (1.56, 0.03, 1.56), (1.6, y / 2 - 0.05, 1.7), root, glass_mat)
        add_cube("blind", (1.62, 0.04, 1.1), (1.6, y / 2 - 0.10, 2.0), root, accent_mat)
        add_cube("desk_top", (1.5, 0.7, 0.04), (1.7, y / 2 - 0.65, 0.74), root, body_mat)
        for index, (px, py) in enumerate(((-0.70, -0.30), (0.70, -0.30), (-0.70, 0.30), (0.70, 0.30))):
            add_cube(
                f"desk_leg_{index + 1}",
                (0.05, 0.05, 0.72),
                (1.7 + px, y / 2 - 0.65 + py, 0.36),
                root,
                dark_mat,
            )
        add_cube("desk_drawer", (0.44, 0.56, 0.15), (2.15, y / 2 - 0.65, 0.62), root, body_mat)
        add_cube("Cabinet", (1.6, 0.45, 2.0), (-2.1, y / 2 - 0.28, 1.0), root, body_mat)
        cdoor = add_cube("cabinet_door", (0.74, 0.02, 0.90), (-2.48, y / 2 - 0.515, 1.45), root, glass_mat)
        add_cube("cabinet_door_frame", (0.74, 0.012, 0.08), (-2.48, y / 2 - 0.525, 1.86), cdoor, body_mat)
        add_cube("cabinet_handle_u", (0.014, 0.014, 0.14), (-2.16, y / 2 - 0.535, 1.42), cdoor, chrome_mat)
        add_cube("cabinet_glass_fixed", (0.74, 0.02, 0.90), (-1.72, y / 2 - 0.515, 1.45), root, glass_mat)
        add_cube("cabinet_door_ll", (0.74, 0.02, 0.85), (-2.48, y / 2 - 0.515, 0.48), root, body_mat)
        add_cube("cabinet_door_lr", (0.74, 0.02, 0.85), (-1.72, y / 2 - 0.515, 0.48), root, body_mat)
        add_cube("cabinet_handle_l", (0.014, 0.014, 0.12), (-2.16, y / 2 - 0.535, 0.62), root, chrome_mat)
        add_cube("cabinet_handle_r", (0.014, 0.014, 0.12), (-2.04, y / 2 - 0.535, 0.62), root, chrome_mat)
        add_cube("WhiteCabinet", (0.9, 0.42, 1.6), (0.2, y / 2 - 0.27, 0.8), root, accent_mat)
        add_cube("cabinet_trim", (0.92, 0.04, 0.04), (0.2, y / 2 - 0.49, 1.62), root, body_mat)
        add_cube("sofa", (1.4, 0.70, 0.42), (-0.2, -1.5, 0.21), root, accent_mat)
        add_cube("sofa_back", (1.4, 0.16, 0.38), (-0.2, -1.78, 0.52), root, accent_mat)
        add_cube("sign", (0.18, 0.02, 0.28), (-x / 2 + 0.08, -0.18, 1.55), root, body_mat)
        add_cube("card_reader", (0.08, 0.03, 0.12), (-x / 2 + 0.08, -0.18, 1.22), root, dark_mat)
        add_cube("door_frame_l", (0.08, 0.10, 2.10), (-x / 2 + 0.03, -1.52, 1.05), root, dark_mat)
        add_cube("door_frame_r", (0.08, 0.10, 2.10), (-x / 2 + 0.03, -0.44, 1.05), root, dark_mat)
        add_cube("door_frame_t", (0.08, 1.18, 0.08), (-x / 2 + 0.03, -0.98, 2.06), root, dark_mat)
        door = add_cube("door", (0.055, 0.94, 2.00), (-x / 2 + 0.05, -0.98, 1.00), root, body_mat)
        add_cylinder(
            "door_knob",
            0.012,
            0.10,
            (-x / 2 + 0.10, -0.56, 1.02),
            door,
            chrome_mat,
            rotation=(0, math.pi / 2, 0),
        )

    else:
        add_cube("Body", (x, y, z), (0, 0, z / 2), root, body_mat)


def import_photogrammetry(glb: Path, spec: dict, root: bpy.types.Object) -> None:
    existing = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    imported = [obj for obj in bpy.data.objects if obj not in existing and obj.type == "MESH"]
    if not imported:
        return
    points = [obj.matrix_world @ Vector(corner) for obj in imported for corner in obj.bound_box]
    minimum = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maximum = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    size = maximum - minimum
    target = Vector(spec["size"])
    scale = min(target[i] / max(size[i], 1e-6) for i in range(3))
    wrapper = bpy.data.objects.new("Photogrammetry", None)
    bpy.context.scene.collection.objects.link(wrapper)
    wrapper.parent = root
    wrapper.scale = (scale, scale, scale)
    wrapper.location = (
        -(minimum.x + maximum.x) * 0.5 * scale,
        -(minimum.y + maximum.y) * 0.5 * scale,
        -minimum.z * scale,
    )
    for obj in imported:
        world = obj.matrix_world.copy()
        obj.parent = wrapper
        obj.matrix_world = world
        obj.name = f"scan_{obj.name[:40]}"


FRICTION = {
    "plastic": (0.45, 0.40, 0.12),
    "painted_wood": (0.50, 0.42, 0.08),
    "wood": (0.55, 0.48, 0.08),
    "metal": (0.30, 0.24, 0.15),
    "fabric": (0.62, 0.55, 0.05),
    "ceramic": (0.40, 0.32, 0.10),
    "cardboard": (0.42, 0.36, 0.06),
    "paper": (0.35, 0.30, 0.04),
}


def hinge_token(joint: dict) -> str:
    if "hinge" in joint:
        return joint["hinge"]
    name = joint["name"]
    if joint["type"] == "prismatic":
        return "origin"
    if name in {"door_left"} or (name.endswith("_left") and "knob" not in name and "lever" not in name):
        return "xmin"
    if name in {"door_right"} or (name.endswith("_right") and "knob" not in name and "lever" not in name):
        return "xmax"
    if name in {"door", "cabinet_door"}:
        return "xmin"
    if name in {"screen", "tilt"}:
        return "zmin"
    if name == "lid":
        return "ymax"
    if name in {"flap", "flap_front"}:
        return "ymin"
    return "origin"


def object_range(prim: Usd.Prim, cache: UsdGeom.BBoxCache):
    bound = cache.ComputeUntransformedBound(prim)
    if hasattr(bound, "ComputeAlignedRange"):
        return bound.ComputeAlignedRange()
    return bound.GetRange()


def hinge_in_part_local(part: Usd.Prim, token: str, cache: UsdGeom.BBoxCache) -> Gf.Vec3d:
    rng = object_range(part, cache)
    minimum, maximum = rng.GetMin(), rng.GetMax()
    mid = (minimum + maximum) * 0.5
    table = {
        "origin": Gf.Vec3d(0, 0, 0),
        "xmin": Gf.Vec3d(minimum[0], mid[1], mid[2]),
        "xmax": Gf.Vec3d(maximum[0], mid[1], mid[2]),
        "ymin": Gf.Vec3d(mid[0], minimum[1], mid[2]),
        "ymax": Gf.Vec3d(mid[0], maximum[1], mid[2]),
        "zmin": Gf.Vec3d(mid[0], mid[1], minimum[2]),
        "zmax": Gf.Vec3d(mid[0], mid[1], maximum[2]),
    }
    return table.get(token, Gf.Vec3d(0, 0, 0))


def set_joint_frames(joint_prim, body: Usd.Prim, part: Usd.Prim, token: str, bbox_cache: UsdGeom.BBoxCache) -> None:
    xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    part_world = xform_cache.GetLocalToWorldTransform(part)
    body_world = xform_cache.GetLocalToWorldTransform(body)
    hinge_world = part_world.Transform(hinge_in_part_local(part, token, bbox_cache))
    p0 = body_world.GetInverse().Transform(hinge_world)
    p1 = part_world.GetInverse().Transform(hinge_world)
    joint_prim.CreateLocalPos0Attr().Set(Gf.Vec3f(float(p0[0]), float(p0[1]), float(p0[2])))
    joint_prim.CreateLocalPos1Attr().Set(Gf.Vec3f(float(p1[0]), float(p1[1]), float(p1[2])))
    joint_prim.CreateLocalRot0Attr().Set(Gf.Quatf(1, 0, 0, 0))
    joint_prim.CreateLocalRot1Attr().Set(Gf.Quatf(1, 0, 0, 0))


def enable_rigid(prim: Usd.Prim, spec: dict, mass_kg: float, density: float, bbox_cache: UsdGeom.BBoxCache) -> None:
    rigid = UsdPhysics.RigidBodyAPI.Apply(prim)
    rigid.CreateRigidBodyEnabledAttr().Set(True)
    if spec["static"] and prim.GetName() in {"Body", "Asset", spec["item_id"]}:
        rigid.CreateKinematicEnabledAttr().Set(True)
    mass = UsdPhysics.MassAPI.Apply(prim)
    mass.CreateMassAttr().Set(float(max(mass_kg, 0.005)))
    mass.CreateDensityAttr().Set(float(density))
    try:
        rng = object_range(prim, bbox_cache)
        size = rng.GetSize()
        sx, sy, sz = max(float(size[0]), 1e-4), max(float(size[1]), 1e-4), max(float(size[2]), 1e-4)
        mass_kg = float(max(mass_kg, 0.005))
        mass.CreateDiagonalInertiaAttr().Set(
            Gf.Vec3f(
                mass_kg * (sy * sy + sz * sz) / 12.0,
                mass_kg * (sx * sx + sz * sz) / 12.0,
                mass_kg * (sx * sx + sy * sy) / 12.0,
            )
        )
        minimum, maximum = rng.GetMin(), rng.GetMax()
        mass.CreateCenterOfMassAttr().Set(
            Gf.Vec3f(
                float((minimum[0] + maximum[0]) * 0.5),
                float((minimum[1] + maximum[1]) * 0.5),
                float((minimum[2] + maximum[2]) * 0.5),
            )
        )
    except Exception:
        pass
    prim.SetCustomDataByKey("semanticLabel", prim.GetName())
    prim.SetCustomDataByKey("partName", prim.GetName())


def add_physics(stage: Usd.Stage, root_path: str, spec: dict) -> None:
    root_prim = stage.GetPrimAtPath(root_path)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    if hasattr(UsdPhysics, "SetStageKilogramsPerUnit"):
        UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)
    stage.SetDefaultPrim(root_prim)
    if spec["joints"]:
        UsdPhysics.ArticulationRootAPI.Apply(root_prim)

    xforms = [prim for prim in stage.Traverse() if prim.GetTypeName() == "Xform"]
    meshes = [prim for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh)]
    moving = {joint["name"] for joint in spec["joints"]}
    named = {prim.GetName(): prim for prim in xforms}
    bbox_cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        [UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
        True,
    )
    static_friction, dynamic_friction, restitution = FRICTION.get(spec["material"], (0.45, 0.40, 0.10))

    for mesh in meshes:
        UsdPhysics.CollisionAPI.Apply(mesh)
        mesh_collision = UsdPhysics.MeshCollisionAPI.Apply(mesh)
        mesh_collision.CreateApproximationAttr().Set("convexHull")
        if hasattr(UsdPhysics, "MaterialAPI"):
            physmat = UsdPhysics.MaterialAPI.Apply(mesh)
            physmat.CreateStaticFrictionAttr().Set(float(static_friction))
            physmat.CreateDynamicFrictionAttr().Set(float(dynamic_friction))
            physmat.CreateRestitutionAttr().Set(float(restitution))

    body = named.get("Body") or named.get("Asset") or root_prim
    n_moving = len([name for name in moving if name in named])
    if n_moving:
        body_mass = max(spec["mass"] * 0.78, 0.04) if spec["mass"] > 0 else 1.0
        part_mass = max((max(spec["mass"], 0.04) - body_mass) / n_moving, 0.008)
    else:
        body_mass = max(spec["mass"], 0.05 if not spec["static"] else 1.0)
        part_mass = 0.0

    if spec["static"]:
        enable_rigid(body, spec, max(spec["mass"], 1.0), spec["density"], bbox_cache)
    else:
        enable_rigid(body, spec, body_mass, spec["density"], bbox_cache)

    for part_name in moving:
        part = named.get(part_name)
        if part is None:
            continue
        density = float(spec.get("part_density", spec["density"]))
        if "knob" in part_name or "button" in part_name:
            density = 1050.0
        enable_rigid(part, spec, part_mass, density, bbox_cache)

    joints_path = f"{root_path}/Joints"
    UsdGeom.Xform.Define(stage, joints_path)
    axis_map = {"x": UsdPhysics.Tokens.x, "y": UsdPhysics.Tokens.y, "z": UsdPhysics.Tokens.z}
    for joint in spec["joints"]:
        part = named.get(joint["name"])
        if part is None:
            continue
        joint_path = f"{joints_path}/{joint['name']}_joint"
        if joint["type"] == "revolute":
            created = UsdPhysics.RevoluteJoint.Define(stage, joint_path)
            created.CreateLowerLimitAttr().Set(float(joint["limits_deg"][0]))
            created.CreateUpperLimitAttr().Set(float(joint["limits_deg"][1]))
        else:
            created = UsdPhysics.PrismaticJoint.Define(stage, joint_path)
            created.CreateLowerLimitAttr().Set(float(joint["limits_m"][0]))
            created.CreateUpperLimitAttr().Set(float(joint["limits_m"][1]))
        created.CreateAxisAttr().Set(axis_map[joint["axis"]])
        created.CreateBody0Rel().SetTargets([body.GetPath()])
        created.CreateBody1Rel().SetTargets([part.GetPath()])
        created.CreateCollisionEnabledAttr().Set(False)
        set_joint_frames(created, body, part, hinge_token(joint), bbox_cache)

    root_prim.SetCustomDataByKey("itemId", spec["item_id"])
    root_prim.SetCustomDataByKey("semanticLabel", spec["label"])
    root_prim.SetCustomDataByKey("pipeline", "automatic_category_prior_plus_video")
    stage.GetRootLayer().Save()


def main() -> None:
    args = parse_args()
    spec = dict(CATALOG[args.item_id])
    spec["item_id"] = args.item_id
    clear_scene()

    root = bpy.data.objects.new("Asset", None)
    bpy.context.scene.collection.objects.link(root)
    texture = args.texture if args.texture and args.texture.exists() else None
    body_mat = make_material("BodyMat", tuple(spec["color"]), spec["material"], texture)
    accent = tuple(spec.get("accent", (0.45, 0.28, 0.16)))
    accent_mat = make_material("AccentMat", accent, "plastic")
    dark_mat = make_material("DarkMat", (0.12, 0.12, 0.13), "plastic")
    chrome_mat = make_material("ChromeMat", (0.74, 0.75, 0.77), "metal")
    glass_mat = make_material("GlassMat", (0.75, 0.82, 0.86), "plastic")
    glass_mat.blend_method = "BLEND"
    if "Alpha" in glass_mat.node_tree.nodes["Principled BSDF"].inputs:
        glass_mat.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.35

    build_geometry(spec, root, body_mat, accent_mat, dark_mat, glass_mat, chrome_mat)
    if args.glb and args.glb.exists():
        import_photogrammetry(args.glb, spec, root)

    output = args.output_usd.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
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
        root_prim_path=f"/{args.item_id}",
        allow_unicode=True,
    )
    stage = Usd.Stage.Open(str(output))
    if stage is None:
        raise RuntimeError(f"USD export failed: {output}")
    add_physics(stage, f"/{args.item_id}", spec)
    print(f"built {args.item_id} -> {output}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
