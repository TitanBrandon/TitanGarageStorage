"""Build an editable, textured room from the reconstruction JSON using headless Blender.

Run with Blender's Python, never a system-Python bpy installation:
blender --background --python backend/blender_build.py -- --scene scene.json --output artifacts

The public scene schema uses meters, Y up and +Z object fronts. This module maps
(x,y,z) to Blender (x,-z,y), then glTF's exporter restores the public coordinates.
It deliberately contains no sample room or fallback reconstruction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import traceback

import bpy
import bmesh
from mathutils import Vector

SCHEMA_VERSION = 1
COLLISIONS: list[dict] = []
MATERIALS: dict = {}
SCENE: dict = {}
OUTPUT: Path
INPUT: Path
TEXTURES: set[str] = set()
WARNINGS: list[str] = []


def progress(stage: str, **details):
    print(json.dumps({"stage": stage, **details}), flush=True)


def number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} must be at most {maximum}")
    return float(value)


def vector(value, label, size=3):
    if not isinstance(value, (tuple, list)) or len(value) != size:
        raise ValueError(f"{label} needs {size} coordinates")
    return [number(item, label, -1000, 1000) for item in value]


def xyz(value):
    x, y, z = value
    return (x, -z, y)


def safe_name(value):
    result = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(value))[:90]
    return result or "material"


def texture_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Texture path must be a nonempty relative path")
    path = (INPUT.parent / value).resolve()
    # Reconstruction outputs belong to the revision directory. Do not expose any
    # machine files via user-controlled JSON or a texture symlink.
    if not path.is_relative_to(INPUT.parent.resolve()):
        raise ValueError("Texture path escapes the scene directory")
    if not path.is_file():
        raise ValueError(f"Missing reconstructed texture: {value}")
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError(f"Texture is too large: {value}")
    return path


def image_texture(nodes, links, path, target, colorspace="sRGB", label=None):
    image = bpy.data.images.load(str(path), check_existing=True)
    image.colorspace_settings.name = colorspace
    image.pack()
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"
    if label:
        tex.label = label
    if target is not None:
        links.new(tex.outputs["Color"], target)
    TEXTURES.add(str(path.relative_to(OUTPUT)) if path.is_relative_to(OUTPUT) else str(path.relative_to(INPUT.parent)))
    return tex


def write_image(path, pixels):
    import numpy as np
    height, width = pixels.shape[:2]
    rgba = np.ones((height, width, 4), dtype=np.float32)
    rgba[:, :, :3] = np.clip(pixels[:, :, :3], 0, 1)
    image = bpy.data.images.new(path.stem, width=width, height=height, alpha=False)
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(rgba.ravel())
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def micro_normal(material_id, spec):
    """A portable tangent-space micro finish; real color always comes from analysis."""
    import numpy as np
    kind = str(spec.get("kind", "")).lower()
    if not any(term in kind for term in ("concrete", "epoxy", "flake", "wood", "metal", "paint", "floor")):
        return None
    seed = int(hashlib.sha256(material_id.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    size = 256
    height = rng.normal(0, .035 if "flake" in kind else .012, (size, size)).astype(np.float32)
    if "wood" in kind:
        height = np.repeat(rng.normal(0, .018, (1, size)), size, axis=0).astype(np.float32) + height * .1
    dy, dx = np.gradient(height)
    nx, ny = -dx, -dy
    nz = np.ones_like(nx)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    rgb = np.stack((nx / norm, ny / norm, nz / norm), axis=-1) * .5 + .5
    path = OUTPUT / "textures" / f"blender_{safe_name(material_id)}_normal.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_image(path, rgb)
    return path


def material(material_id):
    if material_id in MATERIALS:
        return MATERIALS[material_id]
    specs = SCENE.get("materials", {})
    spec = specs.get(material_id)
    if not isinstance(spec, dict):
        raise ValueError(f"Unknown material {material_id!r}; analysis must provide all materials")
    color = vector(spec.get("color", [.55, .55, .55]), f"material {material_id} color")
    if any(c < 0 or c > 1 for c in color):
        raise ValueError(f"Material {material_id} color must be RGB in 0..1")
    mat = bpy.data.materials.new(str(material_id))
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    # Analyzer colors are sRGB samples. Blender shader colors are scene-linear.
    linear = [c / 12.92 if c < .04045 else ((c + .055) / 1.055) ** 2.4 for c in color]
    shader.inputs["Base Color"].default_value = (*linear, 1)
    shader.inputs["Metallic"].default_value = number(spec.get("metalness", spec.get("metallic", 0)), "metalness", 0, 1)
    shader.inputs["Roughness"].default_value = number(spec.get("roughness", .5), "roughness", 0, 1)
    if spec.get("texture"):
        image_texture(nodes, links, texture_path(spec["texture"]), shader.inputs["Base Color"], label="Reconstructed source-image material")
    roughness = spec.get("roughness_texture")
    if roughness:
        image_texture(nodes, links, texture_path(roughness), shader.inputs["Roughness"], "Non-Color")
    normal = spec.get("normal_texture")
    normal_path = texture_path(normal) if normal else micro_normal(str(material_id), spec)
    if normal_path:
        normal_tex = image_texture(nodes, links, normal_path, None, "Non-Color")
        normal_node = nodes.new("ShaderNodeNormalMap")
        normal_node.inputs["Strength"].default_value = .32
        links.new(normal_tex.outputs["Color"], normal_node.inputs["Color"])
        links.new(normal_node.outputs["Normal"], shader.inputs["Normal"])
    mat["source_material_id"] = str(material_id)
    mat["finish"] = str(spec.get("kind", "estimated"))
    MATERIALS[material_id] = mat
    return mat


def internal_material(name, color, roughness=.45, metalness=0):
    if name not in SCENE["materials"]:
        SCENE["materials"][name] = {"color": color, "roughness": roughness, "metalness": metalness, "kind": "metal" if metalness else "paint"}
    return material(name)


def set_uv(mesh, material_id, front_bounds=None):
    spec = SCENE["materials"].get(material_id, {})
    tile = float(spec.get("texture_tile_size", spec.get("tile_size", 1.0)))
    if tile <= 0 or not math.isfinite(tile):
        raise ValueError("texture_tile_size must be positive")
    uv = mesh.uv_layers.new(name="UVMap") if not mesh.uv_layers else mesh.uv_layers.active
    for poly in mesh.polygons:
        n = poly.normal
        main = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            v = mesh.vertices[mesh.loops[li].vertex_index].co
            if front_bounds is not None and main == 1:
                # Front image spans the whole cabinet, even if divided into doors.
                x0, z0, width, height = front_bounds
                coords = ((v.x - x0) / width, (v.z - z0) / height)
            elif main == 2:
                coords = (v.x / tile, v.y / tile)
            elif main == 1:
                coords = (v.x / tile, v.z / tile)
            else:
                coords = (v.y / tile, v.z / tile)
            uv.data[li].uv = coords


def cube(name, center, dimensions, mat, rotation=0, parent=None, bevel=0.006, local=False, front_bounds=None):
    if min(dimensions) <= 0:
        raise ValueError(f"Nonpositive mesh dimensions for {name}")
    bpy.ops.mesh.primitive_cube_add(size=1, location=xyz(center))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = (dimensions[0], dimensions[2], dimensions[1])
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if parent is not None:
        obj.parent = parent
        obj.location = xyz(center)
    obj.rotation_euler.z = rotation
    obj.data.materials.append(mat)
    source_id = mat.get("source_material_id", mat.name)
    set_uv(obj.data, source_id, front_bounds)
    if bevel:
        modifier = obj.modifiers.new("Manufactured edge radius", "BEVEL")
        modifier.width = min(bevel, min(dimensions) / 5)
        modifier.segments = 2
        # Weighted corner normals give cabinet sides clean broad planar faces.
        modifier = obj.modifiers.new("Face-weighted normals", "WEIGHTED_NORMAL")
        modifier.keep_sharp = True
    return obj


def prism(name, polygon, bottom, top, mat):
    n = len(polygon)
    verts = [(x, -z, y) for y in (bottom, top) for x, z in polygon]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, n * 2))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    set_uv(mesh, mat["source_material_id"])
    return obj


def collision_box(name, center, dimensions, rotation=0, category="object"):
    COLLISIONS.append({"id": name, "kind": category, "position": list(center), "dimensions": list(dimensions), "rotation_y": rotation})


def build_room():
    room = SCENE["room"]
    width = number(room.get("width"), "room.width", 1, 100)
    depth = number(room.get("depth"), "room.depth", 1, 100)
    height = number(room.get("height"), "room.height", 1.7, 20)
    polygon = room.get("floor_polygon", [[-width / 2, -depth / 2], [width / 2, -depth / 2], [width / 2, depth / 2], [-width / 2, depth / 2]])
    if not isinstance(polygon, list) or not 3 <= len(polygon) <= 64:
        raise ValueError("room.floor_polygon needs 3..64 points")
    polygon = [vector(point, "floor polygon point", 2) for point in polygon]
    floor_id = room.get("floor_material", "floor")
    floor = prism("Reconstructed floor", polygon, -.12, 0, material(floor_id))
    if not SCENE["materials"][floor_id].get("texture_repeat", True):
        xmin = min(point[0] for point in polygon)
        xmax = max(point[0] for point in polygon)
        zmin = min(point[1] for point in polygon)
        zmax = max(point[1] for point in polygon)
        uv = floor.data.uv_layers.active
        for poly in floor.data.polygons:
            for li in poly.loop_indices:
                v = floor.data.vertices[floor.data.loops[li].vertex_index].co
                uv.data[li].uv = ((v.x - xmin) / (xmax - xmin), (zmax + v.y) / (zmax - zmin))
    if room.get("ceiling", False):
        ceiling_id = room.get("ceiling_material", "ceiling")
        prism("Reconstructed ceiling", polygon, height, height + .10, material(ceiling_id))
    walls = room.get("walls", SCENE.get("walls", []))
    if not isinstance(walls, list) or len(walls) > 64:
        raise ValueError("room.walls must contain at most 64 walls")
    for index, wall in enumerate(walls):
        wall_id = str(wall.get("id", f"wall-{index}"))
        start = vector(wall.get("start"), f"{wall_id}.start", 2)
        end = vector(wall.get("end"), f"{wall_id}.end", 2)
        dx, dz = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dz)
        if length < .05:
            raise ValueError(f"{wall_id} is too short")
        wall_height = number(wall.get("height", height), "wall.height", .1, 20)
        thickness = number(wall.get("thickness", .13), "wall.thickness", .02, 1)
        wall_mat = material(wall.get("material", "wall"))
        # Segment along local X; rotation converts it into schema X/Z space.
        rotation = math.atan2(-dz, dx)
        openings = wall.get("openings", [])
        if not isinstance(openings, list) or len(openings) > 32:
            raise ValueError(f"Invalid openings in {wall_id}")
        cuts = [0., length]
        holes = []
        for opening in openings:
            offset = number(opening.get("offset", 0), "opening.offset", 0, length)
            opening_width = number(opening.get("width"), "opening.width", .05, length)
            bottom = number(opening.get("bottom", 0), "opening.bottom", 0, wall_height)
            opening_height = number(opening.get("height"), "opening.height", .05, wall_height)
            if offset + opening_width > length + .01 or bottom + opening_height > wall_height + .01:
                raise ValueError(f"Opening extends outside {wall_id}")
            finish = min(length, offset + opening_width)
            holes.append((offset, finish, bottom, min(wall_height, bottom + opening_height), opening))
            cuts.extend((offset, finish))
        cuts = sorted(set(cuts))
        part = 0
        for left, right in zip(cuts, cuts[1:]):
            if right - left < .001:
                continue
            midpoint = (left + right) / 2
            vertical_holes = sorted((a[2], a[3]) for a in holes if a[0] <= midpoint <= a[1])
            solid_bands = []
            lower = 0.
            for hole_bottom, hole_top in vertical_holes:
                if hole_bottom > lower:
                    solid_bands.append((lower, hole_bottom))
                lower = max(lower, hole_top)
            if lower < wall_height:
                solid_bands.append((lower, wall_height))
            for low, high in solid_bands:
                if high - low < .001:
                    continue
                center = [start[0] + dx * midpoint / length, (low + high) / 2, start[1] + dz * midpoint / length]
                dims = [right - left, high - low, thickness]
                obj = cube(f"{wall_id} solid {part}", center, dims, wall_mat, rotation=rotation, bevel=.002)
                if not SCENE["materials"][wall_mat["source_material_id"]].get("texture_repeat", True):
                    uv = obj.data.uv_layers.active
                    for poly in obj.data.polygons:
                        for li in poly.loop_indices:
                            v = obj.data.vertices[obj.data.loops[li].vertex_index].co
                            uv.data[li].uv = ((v.x + midpoint) / length, (v.z + (low + high) / 2) / wall_height)
                obj["reconstruction_wall_id"] = wall_id
                collision_box(obj.name, center, dims, rotation, "wall")
                part += 1
        # Thin recessed glazing is real geometry and transparent in both renderers.
        # Doors and garage openings remain physically open; no invisible wall.
        for opening_index, (left, right, low, high, opening) in enumerate(holes):
            if opening.get("kind") not in ("window", "glazing"):
                continue
            window_material = opening.get("material")
            glass = material(window_material).copy() if window_material else internal_material("_window_glass", [.65, .78, .85], .14)
            if window_material:
                glass.name = f"{wall_id} source window {opening_index}"
            shader = glass.node_tree.nodes.get("Principled BSDF")
            transmission = shader.inputs.get("Transmission Weight") or shader.inputs.get("Transmission")
            if transmission:
                transmission.default_value = .08 if window_material else .75
            shader.inputs["Alpha"].default_value = 1 if window_material else .22
            if hasattr(glass, "surface_render_method"):
                glass.surface_render_method = "DITHERED"
            elif hasattr(glass, "blend_method"):
                glass.blend_method = "BLEND"
            midpoint = (left + right) / 2
            center = [start[0] + dx * midpoint / length, (low + high) / 2, start[1] + dz * midpoint / length]
            pane = cube(f"{wall_id} window {opening_index}", center, [right - left, high - low, .012], glass, rotation=rotation, bevel=0)
            if window_material:
                uv = pane.data.uv_layers.active
                for poly in pane.data.polygons:
                    for li in poly.loop_indices:
                        v = pane.data.vertices[pane.data.loops[li].vertex_index].co
                        uv.data[li].uv = (v.x / (right - left) + .5, v.z / (high - low) + .5)
            collision_box(f"{wall_id} window {opening_index}", center, [right - left, high - low, thickness], rotation, "window")
    return width, depth, height


def build_objects():
    objects = SCENE.get("objects", [])
    if not isinstance(objects, list) or len(objects) > 256:
        raise ValueError("objects must contain at most 256 objects")
    for i, spec in enumerate(objects):
        object_id = str(spec.get("id", f"object-{i}"))
        kind = str(spec.get("kind", "box"))
        position = vector(spec.get("position"), f"{object_id}.position")
        w, h, d = vector(spec.get("dimensions"), f"{object_id}.dimensions")
        if min(w, h, d) < .015 or max(w, h, d) > 30:
            raise ValueError(f"Invalid dimensions for {object_id}")
        angle = number(spec.get("rotation_y", 0), "object rotation", -math.tau * 4, math.tau * 4)
        mat_id = spec.get("material")
        mat = material(mat_id)
        front_mat = material(spec.get("front_material") or mat_id)
        group = bpy.data.objects.new(object_id, None)
        bpy.context.collection.objects.link(group)
        group.location = xyz(position)
        group.rotation_euler.z = angle
        group["reconstruction_object_id"] = object_id
        group["kind"] = kind
        group["confidence"] = float(spec.get("confidence", .5))
        if spec.get("wall_id"):
            group["wall_id"] = str(spec["wall_id"])
        def part(name, center, dimensions, use_mat=mat, bevel=.005, front_bounds=None):
            return cube(f"{object_id} {name}", center, dimensions, use_mat, parent=group, bevel=bevel, local=True, front_bounds=front_bounds)
        if kind == "cabinet":
            # Six faces and independent thick door leaves, with a dark seam and a
            # recessed toe kick. No image plane is used for cabinet geometry.
            carcass_depth = max(.02, d - .023)
            part("carcass", [0, 0, -.0115], [w, h, carcass_depth])
            toe_height = min(.085, h * .07) if position[1] - h / 2 < .25 else 0
            if toe_height:
                kick = internal_material("_toe_kick", [.055, .06, .065], .6)
                part("recessed toe kick", [0, -h / 2 + toe_height / 2, d / 2 - .023], [w * .97, toe_height, .012], kick, .002)
            count = max(1, min(6, round(w / .62)))
            gap = .005
            door_width = w / count - gap
            door_height = h - toe_height - .007
            handle_mat = internal_material("_brushed_handles", [.56, .58, .60], .26, .82)
            # Front texture UVs can be rectified across all doors as a continuous
            # front; ordinary finish crops use physical-scale tiling.
            front_spec = SCENE["materials"].get(spec.get("front_material") or mat_id, {})
            full_front = not front_spec.get("texture_repeat", True)
            for door in range(count):
                x = -w / 2 + (door + .5) * w / count
                y = toe_height / 2
                obj = part(f"door {door + 1}", [x, y, d / 2 - .009], [door_width, door_height, .024], front_mat, .003)
                if full_front:
                    uv = obj.data.uv_layers.active
                    for poly in obj.data.polygons:
                        if abs(poly.normal.y) > .9:
                            for li in poly.loop_indices:
                                v = obj.data.vertices[obj.data.loops[li].vertex_index].co
                                uv.data[li].uv = ((v.x + x + w / 2) / w, (v.z + y + h / 2) / h)
                if spec.get("handles", True):
                    side = 1 if door % 2 == 0 and door != count - 1 else -1
                    handle_x = x + side * (door_width / 2 - min(.075, door_width * .20))
                    handle_y = min(.12, h * .12) if h < 1.4 else .12
                    handle_length = min(.24, door_height * .38)
                    part(f"handle {door + 1}", [handle_x, handle_y, d / 2 + .035], [.018, handle_length, .020], handle_mat, .006)
                    for sign in (-1, 1):
                        part(f"handle mount {door + 1}-{sign}", [handle_x, handle_y + sign * handle_length * .36, d / 2 + .012], [.014, .014, .033], handle_mat, .003)
        elif kind in ("slat_wall", "slatwall"):
            # Horizontal channels project correctly from oblique viewpoints.
            backing = internal_material("_slatwall_channel", [.085, .09, .095], .7)
            part("channel backing", [0, 0, -d * .20], [w, h, max(.012, d * .42)], backing, .001)
            pitch = number(spec.get("slat_pitch", .102), "slat pitch", .035, .3)
            count = max(1, math.ceil(h / pitch))
            pitch = h / count
            for slat in range(count):
                part(f"slat {slat + 1}", [0, -h / 2 + (slat + .5) * pitch, d * .22], [w, pitch * .84, max(.012, d * .55)], front_mat, .002)
        elif kind == "workbench":
            top_thickness = min(.065, h * .09)
            part("worktop", [0, h / 2 - top_thickness / 2, 0], [w, top_thickness, d], front_mat)
            leg = min(.075, w * .05, d * .14)
            leg_mat = internal_material("_workbench_frame", [.12, .13, .14], .38, .55)
            for ix in (-1, 1):
                for iz in (-1, 1):
                    part(f"leg {ix} {iz}", [ix * (w / 2 - leg), -top_thickness / 2, iz * (d / 2 - leg)], [leg, h - top_thickness, leg], leg_mat, .002)
            part("lower shelf", [0, -h * .30, 0], [w - leg, .025, d - leg], mat, .002)
        elif kind in ("shelf", "shelving"):
            panel = min(.035, min(w, d) * .07)
            tiers = max(2, min(7, round(h / .42) + 1))
            for level in range(tiers):
                part(f"shelf {level + 1}", [0, -h / 2 + panel / 2 + level * (h - panel) / (tiers - 1), 0], [w, panel, d], front_mat, .002)
            for ix in (-1, 1):
                for iz in (-1, 1):
                    part(f"upright {ix} {iz}", [ix * (w / 2 - panel / 2), 0, iz * (d / 2 - panel / 2)], [panel, h, panel], mat, .002)
        else:
            if kind != "box":
                WARNINGS.append(f"{object_id}: unsupported {kind!r} uses estimated solid bounding geometry")
            obj = part("solid", [0, 0, 0], [w, h, d], mat)
            if spec.get("front_material"):
                # A detected façade may have a rectified door/window texture.
                # Keep it on the actual front face only; unseen sides and rear
                # remain solid finish-colored geometry instead of photo wraps.
                obj.data.materials.append(front_mat)
                uv = obj.data.uv_layers.active
                for poly in obj.data.polygons:
                    # Public +Z maps to Blender -Y before the object rotation.
                    if poly.normal.y < -.9:
                        poly.material_index = len(obj.data.materials) - 1
                        for li in poly.loop_indices:
                            v = obj.data.vertices[obj.data.loops[li].vertex_index].co
                            uv.data[li].uv = (v.x / w + .5, v.z / h + .5)
        collision_box(object_id, position, [w, h, d], angle, kind)


def setup_camera():
    camera_spec = SCENE.get("camera")
    if not isinstance(camera_spec, dict):
        raise ValueError("Scene must contain the reconstructed source camera")
    position = vector(camera_spec.get("position"), "camera.position")
    target = vector(camera_spec.get("target"), "camera.target")
    if (Vector(position) - Vector(target)).length < .05:
        raise ValueError("camera.position and target must be distinct")
    data = bpy.data.cameras.new("Source photograph perspective")
    camera = bpy.data.objects.new("Source camera (separate from walking)", data)
    bpy.context.collection.objects.link(camera)
    camera.location = xyz(position)
    direction = Vector(xyz(target)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    aspect = number(camera_spec.get("aspect", SCENE.get("source", {}).get("aspect", 4 / 3)), "camera.aspect", .1, 8)
    fov = math.radians(number(camera_spec.get("fov", 60), "camera.fov", 15, 120))
    # Blender's angle is horizontal with horizontal sensor fit. Convert a public
    # vertical FOV using the actual source aspect to preserve image alignment.
    horizontal = fov if camera_spec.get("fov_axis") == "horizontal" else 2 * math.atan(math.tan(fov / 2) * aspect)
    data.sensor_fit = "HORIZONTAL"
    data.angle = horizontal
    data.clip_start = .025
    data.clip_end = 500
    camera["purpose"] = "source_photo_comparison"
    bpy.context.scene.camera = camera
    return camera, aspect


def light(name, kind, center, energy, color, size=1, target=None):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = color
    if kind == "AREA":
        data.shape = "DISK"
        data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = xyz(center)
    if target is not None:
        obj.rotation_euler = (Vector(xyz(target)) - obj.location).to_track_quat("-Z", "Y").to_euler()
    obj["preview_only"] = True
    return obj


def setup_lighting(width, depth, height):
    world = bpy.data.worlds.new("Neutral daylight environment")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (.76, .82, .91, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = .25
    bpy.context.scene.world = world
    # Physically sized diffuse fixtures, not point lights that burn the floor.
    # Export excludes these preview lights; browser supplies its renderer lights.
    light("Soft interior bounce", "AREA", [0, height - .12, 0], max(180, width * depth * 6), (1.0, .93, .85), min(width, depth) * .7, [0, 0, 0])
    light("Entrance daylight", "AREA", [0, height * .7, depth / 2 + .3], max(250, width * depth * 9), (.81, .89, 1), width * .7, [0, height * .35, -depth * .25])
    sun = light("Daylight sun", "SUN", [-width, height * 3, depth], .7, (1.0, .96, .90), target=[0, 0, 0])
    sun.data.angle = math.radians(12)


def prepare_render(aspect, samples, resolution):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = .025
    scene.cycles.adaptive_min_samples = min(16, samples)
    scene.cycles.sample_clamp_direct = 8
    scene.cycles.sample_clamp_indirect = 2
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    # Distribution Blender builds may lack OpenImageDenoise. This is a
    # capability check, not a failed-render retry or a GPU dependency.
    try:
        import _cycles
        scene.cycles.use_denoising = bool(_cycles.with_openimagedenoise)
    except (ImportError, AttributeError):
        scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 5
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 3
    # Use bounded CPU parallelism inside the worker; no GPU or display required.
    scene.render.threads_mode = "FIXED"
    scene.render.threads = max(1, min(8, int(os.environ.get("BLENDER_THREADS", "4"))))
    if aspect >= 1:
        scene.render.resolution_x = resolution
        scene.render.resolution_y = max(96, round(resolution / aspect))
    else:
        scene.render.resolution_x = max(96, round(resolution * aspect))
        scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(OUTPUT / "preview.png")
    # A photographic display transform rolls off highlights instead of
    # clipping the brighter photo-derived floor finish to solid white.
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        scene.view_settings.view_transform = "Filmic"
    try:
        scene.view_settings.look = "None"
    except TypeError:
        scene.view_settings.look = "None"
    scene.view_settings.exposure = -.35
    scene.view_settings.gamma = 1
    # Exposure-consistent RGB export for the browser's sRGB textures.
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"


def export_glb():
    # Preview lighting never gets imported on top of the browser's own lighting.
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        if obj.type in ("MESH", "EMPTY", "CAMERA"):
            obj.select_set(True)
    desired = {
        "filepath": str(OUTPUT / "scene.glb"),
        "export_format": "GLB",
        "use_selection": True,
        "export_yup": True,
        "export_apply": True,
        "export_texcoords": True,
        "export_normals": True,
        "export_materials": "EXPORT",
        "export_extras": True,
        "export_cameras": True,
        "export_lights": False,
        "export_animations": False,
        "export_draco_mesh_compression_enable": False,
    }
    supported = set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
    result = bpy.ops.export_scene.gltf(**{key: value for key, value in desired.items() if key in supported})
    if "FINISHED" not in result:
        raise RuntimeError("Blender glTF export did not finish")


def validate_artifacts(skip_preview):
    glb = OUTPUT / "scene.glb"
    with glb.open("rb") as stream:
        import struct
        header = stream.read(12)
        if len(header) != 12:
            raise RuntimeError("Empty GLB output")
        magic, version, length = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2 or length != glb.stat().st_size:
            raise RuntimeError("Invalid glTF2 binary output")
        chunk_len, chunk_type = struct.unpack("<II", stream.read(8))
        if chunk_type != 0x4E4F534A:
            raise RuntimeError("GLB has no JSON scene")
        document = json.loads(stream.read(chunk_len))
    if not document.get("meshes"):
        raise RuntimeError("GLB contains no actual mesh geometry")
    for img in document.get("images", []):
        if "bufferView" not in img:
            raise RuntimeError("GLB references an external image; textures must be embedded")
    if not (OUTPUT / "scene.blend").is_file():
        raise RuntimeError("Editable Blender project missing")
    if not skip_preview and not (OUTPUT / "preview.png").is_file():
        raise RuntimeError("Source-camera preview missing")
    return document


def build(args):
    global SCENE, INPUT, OUTPUT
    INPUT = Path(args.scene).resolve()
    OUTPUT = Path(args.output).resolve()
    if not INPUT.is_file() or INPUT.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Scene description must be an existing JSON file below 8 MiB")
    SCENE = json.loads(INPUT.read_text())
    if not isinstance(SCENE, dict) or not isinstance(SCENE.get("room"), dict) or not isinstance(SCENE.get("materials"), dict):
        raise ValueError("Invalid reconstruction: room and materials are required")
    if SCENE.get("schema_version", SCENE.get("version", 1)) not in (1, "1", "1.0"):
        raise ValueError("Unsupported scene schema version")
    if len(SCENE["materials"]) > 128:
        raise ValueError("Too many reconstructed materials")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # Clean scene data, never wipe the revision directory or any repository files.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    progress("building_geometry", blender_version=bpy.app.version_string)
    width, depth, height = build_room()
    build_objects()
    camera, aspect = setup_camera()
    setup_lighting(width, depth, height)
    prepare_render(aspect, args.samples, args.resolution)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1
    bpy.context.scene["scene_schema"] = SCHEMA_VERSION
    bpy.context.scene["source_camera"] = json.dumps(SCENE["camera"])
    bpy.context.scene["walk_start"] = json.dumps(SCENE.get("walk_start", SCENE["camera"]))
    bpy.context.scene["reconstruction_warnings"] = json.dumps(SCENE.get("warnings", SCENE.get("analysis", {}).get("warnings", [])))
    # Disable backup files, leaving exactly the user-requested editable project.
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "scene.blend"))
    progress("exporting_glb")
    export_glb()
    if not args.skip_preview:
        progress("rendering_preview", engine="CYCLES", device="CPU", samples=args.samples)
        bpy.ops.render.render(write_still=True)
    document = validate_artifacts(args.skip_preview)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "builder": "Blender structured-scene reconstruction",
        "blender_version": bpy.app.version_string,
        "coordinate_system": "Y-up, meters, object-front +Z",
        "artifacts": {"blend": "scene.blend", "glb": "scene.glb", "preview": None if args.skip_preview else "preview.png", "scene": INPUT.name},
        "mesh_count": len(meshes),
        "vertex_count": sum(len(mesh.data.vertices) for mesh in meshes),
        "triangle_count": sum(sum(len(poly.vertices) - 2 for poly in mesh.data.polygons) for mesh in meshes),
        "gltf_mesh_count": len(document.get("meshes", [])),
        "gltf_material_count": len(document.get("materials", [])),
        "embedded_texture_count": len(document.get("images", [])),
        "texture_names": sorted(TEXTURES),
        "camera": SCENE["camera"],
        "walk_start": SCENE.get("walk_start", SCENE["camera"]),
        "room": {"width": width, "depth": depth, "height": height, "floor_polygon": SCENE["room"].get("floor_polygon")},
        "collisions": COLLISIONS,
        "source": SCENE.get("source", {}),
        "warnings": SCENE.get("warnings", SCENE.get("analysis", {}).get("warnings", [])) + WARNINGS,
        "validation": {"glb_version": 2, "embedded_textures": True, "has_real_meshes": True, "preview_renderer": None if args.skip_preview else "Cycles CPU"},
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    progress("complete", mesh_count=len(meshes), embedded_texture_count=len(document.get("images", [])), output=str(OUTPUT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--resolution", type=int, default=640)
    parser.add_argument("--skip-preview", action="store_true", help="Development-only export; production requires a rendered preview")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parser.parse_args(argv)
    if not 4 <= args.samples <= 128 or not 256 <= args.resolution <= 1536:
        parser.error("samples must be 4..128; resolution must be 256..1536")
    try:
        build(args)
    except Exception as exc:
        progress("failed", error=str(exc))
        traceback.print_exc()
        # Blender commonly returns zero for script exceptions unless explicitly
        # terminated. The job worker must see failure rather than partial output.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)


if __name__ == "__main__":
    main()
