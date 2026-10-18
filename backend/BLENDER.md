# Headless reconstructed-scene builder

The production worker runs Blender after `reconstruction.py` has analyzed an
uploaded photograph and saved a validated `scene.json` plus material textures.
The builder consumes those estimates; it never generates a sample garage as a
fallback. Failed geometry, missing textures, invalid coordinates, and failed
exports exit nonzero and leave the job in an error state.

Run from the existing checkout (each cloud task is already isolated; a second
Git worktree is unnecessary):

```sh
blender --background --python backend/blender_build.py -- \
  --scene /absolute/project/revision/scene.json \
  --output /absolute/project/revision
```

Use the distribution Blender package installed by the project's Dockerfile.
The builder has been executed with Blender **4.3.2**, CPU Cycles, on Linux.
The production image pins Debian Blender **3.4.1+dfsg-2+b1** and its distinct
`python3-numpy` package **1:1.24.2-1+deb12u1**. Debian Blender embeds Python 3.11;
the analysis server runs Python 3.12 with separately pinned pip dependencies.
Installing NumPy into the analysis interpreter does not install it for Blender.
Both build stages run `blender_smoke.py`, first as root and then as final UID
10001, exporting a real textured GLB and editable `.blend` in temporary writable
storage. `--python-exit-code 1` makes missing imports/exporter failures fail the
Docker build. This packaging check is separate from actual photo validation. It
uses APIs shared with Blender 3.4 LTS; the exact deployed version and build
capabilities appear in each result's manifest. Blender bundles `bpy`, `bmesh`,
`mathutils`, and NumPy; do not install a separate `bpy` wheel. No GPU, X server,
Blender add-on, paid API, or external material download is required. Distribution
builds without OpenImageDenoise automatically render without that optional
filter; they still use Cycles and return a real preview. Blender is GPL-licensed;
rendered outputs and users' models are not automatically covered by that
license. Source image and reconstruction model licenses remain separate.

The worker owns cancellation, process groups, concurrency, deadlines, and job
state. `BLENDER_THREADS` bounds render threads (default 4, maximum 8). The
builder defaults to 640 pixels on the longer source-image dimension and 64
samples; `--resolution` and `--samples` can override that for validation or
higher-quality output. `--skip-preview` is for development exports only;
production output validation requires `preview.png`.

## Input and coordinates

`scene_schema.py` defines the validated public contract. Coordinates are
estimated meters, Y up. Objects have center positions and width/height/depth.
Their front faces point local +Z; positive `rotation_y` rotates +Z toward +X.
The back wall is normally -Z. The builder maps `(x,y,z)` to Blender `(x,-z,y)`
and the glTF exporter restores the public coordinates. The source camera's
`fov_axis` identifies whether its degrees describe vertical or horizontal FOV.
The separate `walk_start` is preserved without moving the source camera.

The floor follows `room.floor_polygon`. Wall segments are independent thick
meshes; opening bounds split solid geometry horizontally and vertically, so a
door is a physical opening rather than a transparent picture. Windows have
recessed glazing. Cabinet bodies, doors, seams, handles, toe kicks, workbench
legs, shelf uprights, and slat-wall channels have real depth. Supported object
geometry remains coherent from the side and rear. The builder uses the detected
position, size, orientation, and wall reference rather than relocating fixtures
into a generic showroom.

Materials use Principled BSDF nodes with exportable base color, metalness,
roughness, and normal maps. Image color textures come from the analysis output.
They are packed into both `.blend` and `.glb`. Material patches tile in meters
using `texture_tile_size`; `texture_repeat: false` maps a rectified floor or
wall across its estimated extent. An optional cabinet `front_material` can map
a rectified front continuously across separate physical door leaves. Sides and
backs retain their own finish. Detected box-shaped structures can also carry
an optional `front_material` on the +Z front face alone, with full-front UVs;
their side, rear, top, and bottom surfaces keep the estimated solid finish. Small deterministic normal maps supply micro
finish without turning the full photo into geometry. Slat walls have physical
strips and recessed grooves. The analyzer's floor texture supplies any detected
flake pattern at the estimated tile scale; the builder does not invent a flake
floor for every room.

The Cycles preview uses the estimated source camera and neutral interior/daylight
lighting. Lights used for the still are excluded from GLB export; the browser
supplies Three.js lighting, reflections, shadows, and tone mapping. A preview
is therefore one comparison view, not proof of browser fidelity.

## Output and validation

- `scene.blend`: editable, metric Blender scene with packed textures and a named
  source camera; scene custom properties include walking and source metadata.
- `scene.glb`: glTF 2 binary with embedded color/normal images, evaluated bevels,
  normals, UV coordinates, real mesh geometry, and reconstructed-object extras.
- `preview.png`: CPU Cycles source-camera view matching the source aspect ratio.
- `manifest.json`: artifact names, Blender version, public coordinate system,
  source/walking cameras, collision boxes, material/mesh/vertex/triangle counts,
  embedded-image count, texture filenames, and reconstruction warnings.

Textures must be existing files inside the scene JSON's directory. Path escapes
and symlinks pointing outside that directory are rejected. The builder checks
GLB magic, version, size, actual mesh presence, and embedded images before
reporting completion. Its line-delimited JSON progress messages identify
geometry, export, preview, completion, and failure stages. The backend also
validates artifact headers before exposing downloads.

This stage cannot recover unseen details or prove metric accuracy from one
image. Appearance and geometry quality depend on analysis confidence, source
coverage, and the optional correction controls. Unsupported detected object
classes receive explicit warnings if supplied directly; the production schema
limits the supported classes. Keep those limitations with the resulting model.
