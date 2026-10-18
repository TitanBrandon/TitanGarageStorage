"""Build-time Blender-runtime check; run via Blender, never system Python.

Checks the Blender-owned Python/NumPy, glTF add-on, packed textures, editable
project output, and writable temporary space under the final container UID.
This is packaging validation, not photo-reconstruction or appearance evidence.
"""
from pathlib import Path
import json
import os
import struct
import sys
import tempfile

import bpy
import numpy as np

expected_uid = int(sys.argv[sys.argv.index("--expect-uid") + 1]) if "--expect-uid" in sys.argv else 0
assert os.geteuid() == expected_uid, f"Blender runs as UID {os.geteuid()}, expected {expected_uid}"
assert bpy.app.version >= (3, 4, 0), "Blender 3.4 or newer is required"
assert np.isfinite(np.array([1.0])).all()

with tempfile.TemporaryDirectory(prefix="titan-blender-smoke-") as scratch:
    scratch = Path(scratch)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=1)
    cube = bpy.context.object
    mat = bpy.data.materials.new("packaging texture check")
    mat.use_nodes = True
    cube.data.materials.append(mat)
    image = bpy.data.images.new("smoke source texture", width=2, height=2, alpha=False)
    image.pixels.foreach_set(np.ones(16, dtype=np.float32))
    image.filepath_raw = str(scratch / "texture.png")
    image.file_format = "PNG"
    image.save()
    image.pack()
    texture = mat.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    mat.node_tree.links.new(texture.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    blend_path, glb_path = scratch / "smoke.blend", scratch / "smoke.glb"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", export_yup=True)
    assert blend_path.read_bytes().startswith(b"BLENDER"), "Blender project was not written"
    data = glb_path.read_bytes()
    magic, version, length = struct.unpack("<4sII", data[:12])
    assert magic == b"glTF" and version == 2 and length == len(data), "Invalid GLB output"
    json_len, json_kind = struct.unpack("<II", data[12:20])
    assert json_kind == 0x4E4F534A
    document = json.loads(data[20:20 + json_len])
    assert document.get("meshes"), "glTF exporter omitted actual geometry"
    assert document.get("images") and all("bufferView" in im for im in document["images"]), "glTF textures were not embedded"
    print(json.dumps({"blender_packaging_check": "passed", "uid": os.geteuid(), "blender": bpy.app.version_string, "python": sys.version.split()[0], "numpy": np.__version__}), flush=True)
