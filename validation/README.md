# Actual photo-to-Blender validation

This implementation is a working **experimental planar reconstruction pipeline**.
The captured results remain below the requested photorealistic standard. Passing
pipeline and navigation tests does not establish a faithful scan of the property.
The comparisons below show the current results, including their errors.

## Inputs and generated deliverables

Two different real photographed interiors were uploaded through the authenticated
production web server to the worker. Each input was analyzed independently with
the local depth model and geometric methods, then processed by actual headless
**Blender 3.4.1**, rendered with CPU Cycles, and exported with embedded textures.
No paid generation API, prebuilt room model, or mocked reconstruction was used.

The original inputs are permitted CC0 perspective crops of captured Poly Haven
HDR photographs. Their provenance, hashes, crop method and low-resolution limits
are documented in [photos/README.md](photos/README.md). The original dealership
photo was not available as a local input and is outside the supported bounded
interior/vehicle reconstruction range.

| Input | Estimated room, metres | Meshes / embedded images | Files |
| --- | --- | --- | --- |
| [Warehouse photo](photos/warehouse.jpg) | 6.05 × 7.51 × 2.70 | 10 / 13 | [Comparison](results/warehouse-source.png), [Cycles preview](results/warehouse-blender.png), [walk](results/warehouse-walk.png), [look back](results/warehouse-back.png), [GLB](results/warehouse.glb), [Blender project](results/warehouse.blend) |
| [Residential photo](photos/room.jpg) | 4.62 × 4.56 × 2.70 | 9 / 9 | [Comparison](results/room-source.png), [Cycles preview](results/room-blender.png), [walk](results/room-walk.png), [look back](results/room-back.png), [GLB](results/room.glb), [Blender project](results/room.blend) |

The warehouse produced a real partition/annex box and a window hypothesis; the
residential scene produced two doorway hypotheses. Source image hashes, room
geometry, objects and material signatures differ between uploads. The GLBs are
approximately 963 KiB and 569 KiB. The editable Blender projects pack their images.
The `.blend` and GLB files open independently of the worker's texture directory.

The `warehouse/` and `room/` directories hold reproducible analysis fixtures,
masks, source-derived textures and overlays. `results/*-scene.json` and manifests
come from the actual HTTP worker jobs. The worker normalizes uploaded images to
JPEG, so its source hashes and small geometric estimates can differ from the
reference analysis of the original fixture JPEGs. Browser evidence records the
actual normalized source hash and model hash for each job.

## What was verified

- The web and worker Docker images build with pinned packages, a checksum-verified
  depth model, and trusted Debian Blender packages. Blender's separate Python
  3.11 NumPy dependency and textured export are checked at build time, including
  as the final unprivileged UID 10001.
- **46 backend tests passed**, including actual ONNX inference, scene edits,
  authentication, durable queue/leases, timeouts, cancellation, failure handling,
  and proxy behavior.
- **Six browser checks passed**: two complete real-photo processing/navigation
  tests, one real malformed-upload/API test, and three explicitly mocked
  unavailable-worker/mobile presentation checks. The presentation checks do not
  constitute reconstruction evidence.
- Both real upload requests returned saved project and job IDs before processing
  finished. Reloading during processing reconnected to the same job without a
  duplicate upload; completed projects reopened after another page reload.
- The browser loaded actual GLB geometry and embedded textures without page
  errors, used the scene's separate source camera, moved sideways/forward/back,
  maintained eye height, stopped at modeled obstacles, looked back, and reset.
  The warehouse camera stopped ahead of the modeled annex rather than crossing
  its volume. Escape releases pointer capture so toolbar controls remain usable.
- Completed projects and protected GLB downloads survived a worker restart.
  A separate new container reopened the named volume after the original web and
  worker containers were removed, verifying storage outside their writable layers.
- Additional real HTTP lifecycle checks exercised unsupported blank-image
  failure without a replacement model, cancellation of a running photo job,
  interrupted-job recovery, and unauthenticated download rejection.

Machine-readable evidence is in [runtime.json](results/runtime.json),
[warehouse-browser.json](results/warehouse-browser.json),
[room-browser.json](results/room-browser.json), and
[operations.json](results/operations.json). Manifests identify the actual Blender
version, mesh/texture counts, source camera and collision geometry.

## Visual review and remaining gaps

The source views retain the corresponding room's dominant finishes and visible
wall details, and the warehouse partition has real depth and side surfaces.
Moving to another viewpoint reveals coherent meshes, including an explicitly
estimated wall behind the source camera. This does **not** recover unseen imagery.

Material and geometry errors remain substantial:

- The warehouse annex proportions are approximate; its joinery, ceiling beams,
  bench, small clutter and other structures are omitted or remain flattened in
  surface textures. It is not a measured reconstruction of that building.
- One residential recess can be misclassified as another open doorway. Space
  beyond openings is unknown, and the wooden door is represented in a wall
  texture rather than reconstructed door joinery.
- Floor texture repetition and large lighting seams were corrected, but the
  small source photographs still limit finish detail. Lighting is estimated;
  photographed shadows and reflections are partly baked into wall materials.
- Focal calibration can use a disclosed 67° horizontal prior; these test crops
  were made with 90° fields of view. Dimensions and perspective therefore need
  review and optional correction. No ground-truth metric accuracy is claimed.
- The unobserved wall has an estimated sampled finish. A ceiling is omitted when
  its junction is not established. Neither is an observation of hidden geometry.
- Actual cabinet/slat recognition has not been demonstrated by these two empty
  interior fixtures. The builder separately passed cabinet/slat/bench mechanical
  tests, which do not establish recognition on a real cabinet photograph.
- Vehicles, mirrors, complex clutter and the original open-sided showroom are
  unsupported. Faithful reconstruction of those details needs more observations
  and a suitable multi-view/semantic reconstruction method.

## Repeat the checks

Use Python 3.12 with the worker requirements, Docker on Linux, Node dependencies
and Chromium installed. Run from the repository:

```sh
python scripts/validate_pipeline.py --cloud-network
# Outside the managed cloud, omit --cloud-network.
# To reuse already built final images:
python scripts/validate_pipeline.py --skip-build
```

The helper starts owned production web/worker containers on 8023/8022, uses
random temporary test credentials without printing them, runs the real browser
suite, tests durable storage, and removes only its own containers. It retains a
uniquely named project volume; `runtime.json` records its exact cleanup command.
Existing local services and production credentials are not reused or changed.
The worker is limited to 4 CPUs/8 GiB and the web container to 1 CPU/512 MiB;
resource samples are recorded. These test limits do not establish the actual
resources of the existing Render service.

Reproduce the input crops using `python scripts/make_photo_fixtures.py`; source
HDR checksums are verified before projection. Backend tests run with
`python -m unittest discover -s backend -p 'test_*.py' -v`.

## Deployment boundary

The existing Render URL and account resources could not be inspected or changed:
no Render account credentials were available, and the cloud's egress proxy
returned HTTP 403 for the live site and Render API. Local Docker success is not
proof of deployment. The existing website needs a durable worker host, a stable
HTTPS endpoint, matching worker authentication and a manual deployment of the
new commit. Exact steps are in [DEPLOY.md](../DEPLOY.md).
