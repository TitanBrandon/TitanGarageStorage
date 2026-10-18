# Local photo reconstruction

`backend.reconstruction.analyze_photo(source_path, output_dir, progress=None,
cancelled=None)` runs the CPU analysis used by the portable reconstruction worker.
It does not call World Labs, an LLM, or any paid image-generation service.

This first implementation is an **estimated planar interior model**. It is useful
for trying room geometry and navigation, but it is not a photogrammetric survey
or a general solution for photorealistic reconstruction from one photograph.
Do not advertise a successful job as an accurate copy of the property.

## Supported input and automatic analysis

Use a reasonably straight, wide photograph of a bounded garage or room. Show a
large patch of floor, the floor/wall junction, and long structural edges. Empty
or lightly furnished rooms work best. The first validation inputs are real
captured warehouse and residential interior photographs; provenance is recorded
with the validation artifacts. Analysis requires at least 192 pixels on both
image axes; an upload accepted by the web form can still fail this analysis check.

1. EXIF orientation is applied, and the working image is resized to at most
   1024 pixels on its longest side. The job store preserves its normalized JPEG
   upload; it does not preserve the original file's bytes or EXIF metadata.
2. The existing checksum-pinned Depth Anything V2 Small ONNX model estimates
   relative inverse depth on CPU. The model is verified before inference. Its
   output is not treated as measured metres.
3. Deterministic RANSAC fits affine inverse-depth planes. A substantial connected
   floor region must reach the bottom of the image; fitted floor support is
   recorded, together with the plane coefficients and mask.
4. OpenCV's line-segment detector supplies long horizontal/vertical candidates.
   Clusters of converging lines estimate the forward vanishing point. Structural
   edges and the fitted floor select the visible wall boundary rectangle. A
   broad upper edge is required before a ceiling is built; a door header is not
   silently treated as a low roof.
5. The pinhole camera uses the inferred horizon/pitch. Where focal calibration is
   ambiguous it uses a disclosed 67-degree horizontal field-of-view prior.
   A 2.7 m ceiling prior anchors scale, subject to a plausible eye-height bound.
   Room dimensions and the source camera are solved together from the visible
   back-wall boundaries. Cropped corners and weak vanishing points produce
   explicit warnings.
6. Positive depth residuals, compact closed silhouettes and rectangular line
   groups identify box-like objects on the back, left and right walls. Objects
   are intersected with the corresponding wall plane, given estimated physical
   depth, and anchored with the appropriate wall-facing rotation. Cabinet-like
   rectangles and regular horizontal slat bands use conservative heuristics;
   this is not a trained cabinet semantic segmenter. Unknown enclosure shapes
   remain labelled `box`. Cropped wall/ceiling regions are not promoted to
   furniture. Semantic confidence is shown in the scene data.
7. Rectangular negative depth residuals indicate possible recessed openings.
   Very bright bounded rectangles additionally support window hypotheses.
   Ground-adjacent door openings are snapped to the floor. Openings and object
   bounds require review when precision matters.
8. Floor material samples are rectified through the solved ground plane and
   assigned an estimated metre scale. Broad illumination is removed from the
   finish sample and a mirrored periodic tile avoids repeated bright/dark
   checkerboard seams while preserving the source grain at its estimated scale.
   Each visible wall has its own rectified
   source material; foreground object pixels are removed from the underlying
   wall. Independently reconstructed objects have separate front crops and
   coherent finish-colored sides. Window crops belong to separate glazing
   meshes. This is not a single image used as a displaced plane or a photograph
   placed across every side of a room. A solid wall behind the source camera
   closes the walkable space using only the sampled wall finish. This wall is
   explicitly marked `front-estimated`; its shape and lack of openings are
   conservative estimates, not recovered observations.

The structured scene passes `backend.scene_schema.SceneDescriptor` validation
before it reaches Blender. The builder creates actual walls with holes,
floor/ceiling meshes, and closed boxes/cabinets/slat strips, rather than exporting
the depth image as the finished scene.

## Runtime, dependencies and models

Use the pinned worker requirements: NumPy 2.2.6, Pillow 11.3.0, OpenCV headless,
ONNX Runtime 1.22.1 and Pydantic 2.x. The dependency lock is maintained in
`requirements-worker.txt`. Python 3.12 is the reference runtime. No GPU is
required. Inference is limited to four CPU threads and jobs are bounded by the
worker's configured concurrency and timeout. A worker with at least four CPU
cores and 8 GiB RAM is recommended for the analysis plus headless Blender;
Render's small free web instance is not the reconstruction worker.

`TITAN_DEPTH_MODEL_PATH` may point to the preinstalled model. Otherwise the
analyzer uses `backend/models/depth_anything_v2_vits.onnx`. The existing
`python -m backend.download_model` command downloads the fixed 99,373,606-byte
release and verifies SHA-256
`d2b11a11c1d4a12b47608fa65a17ee9a4c605b55ee1730c8e3b526304f2562be`.
No runtime network download is attempted by the analyzer.

Depth Anything V2 **Small** weights are Apache-2.0 licensed. The Base/Large/Giant
models have different licensing and are not substituted. The ONNX conversion
comes from fabio-sim/Depth-Anything-ONNX v2.0.0. See `MODELS.md` and
`THIRD_PARTY_NOTICES.txt` for upstream attribution and the pinned source.
OpenCV is Apache-2.0; ONNX Runtime is MIT; NumPy uses BSD-3-Clause; Pillow uses
the HPND license. Blender is a separate GPL-licensed executable.

## Outputs and scene contract

The job directory contains `scene.json`, `relative_depth.npy`, `depth.png`,
`floor-mask.png`, `wall-mask.png`, `analysis-overlay.jpg`, and source-derived
PNG files under `textures/`. The source photo, preview, `.blend` and `.glb`
are managed by the worker/job pipeline. Diagnostic masks are analysis evidence,
not 3D deliverables.

Scene version 1 uses **Y-up**, forward **-Z**, and `estimated_meters` units. The
rear wall lies at `z=-depth/2`, the entry lies toward `+Z`, and the floor is at
`y=0`. `room.walls` is nested in `room`; each wall contains start/end `[x,z]`,
height, material and optional openings. Opening `offset` is the start distance
along the wall from `wall.start`. `bottom` is height above the floor. Object
`position` is the center; `dimensions` is `[width,height,depth]`; front faces
point local `+Z` before `rotation_y` in radians. Left-wall objects face `+X`
and right-wall objects face `-X`. Materials carry sRGB color, roughness,
metalness, an optional safe relative PNG path, `texture_repeat` and
`texture_tile_size` in metres. The source camera's `fov` is vertical degrees.
`walk_start` is separate from `camera`.

`apply_corrections(scene, corrections)` validates and applies optional edits:

```json
{
  "room": {"width": 6.0, "depth": 7.5, "height": 2.8},
  "camera": {"fov": 62, "pitch": -8},
  "wall_corners": [[-3,-3.75],[3,-3.75],[3,3.75],[-3,3.75]],
  "objects": [{"id":"back-object-1","position":[0,1,-3.2],"dimensions":[2,2,0.6]}]
}
```

Camera pitch corrections are degrees. Room edits scale geometry, source/walk
cameras, openings and object local dimensions coherently. Convex wall-corner
edits preserve wall IDs and source materials, rotate attached objects with their
wall, and keep their normal offset. Unknown object IDs, self-intersecting
corners, unsafe textures and nonfinite dimensions are rejected.

## Known limits and failure behavior

The original open-sided car-showroom photograph is outside the initial bounded
interior target: cars, glass, open sky, foliage and hidden vehicle backs cannot
be reconstructed faithfully by these methods. Use additional photos/video and
a suitable multi-view reconstruction system for a measured, convincing model of
that scene. This implementation must not claim to have reconstructed the cars.

The pipeline rejects insufficient floor support, missing structural edges and
unreadable/undersized images. It never swaps an unsupported upload for a sample
garage. A completed scene can still carry substantial uncertainty: curved or
non-Manhattan spaces, heavy occlusion, mirrors/glass, arbitrary furniture,
small objects, ceiling beams, exact door joinery and hidden rooms remain
unsupported or simplified. There is no semantic foundation model for these
features. Texture shadows can remain baked in; unobserved surfaces get sampled
finish colors, and source-camera perspective can need correction. Side views
are geometrically coherent approximations but not recovered photographs.

The warehouse validation detects a real freestanding partition as an uncertain
box, not an accurately modeled annex with every stud or door. The residential
validation detects the two visible recessed regions as doorway hypotheses;
space beyond those openings is not measured. These limitations must accompany
the previews instead of being hidden behind a success indicator.
