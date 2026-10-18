# Reconstruction models and runtime

The worker uses **Depth Anything V2 Small** as a relative-depth input to locally executed geometric reconstruction. Depth is combined with perspective/edge analysis, major surface separation, supported object hypotheses and source-derived material regions. Blender then builds room and object meshes with real depth and side surfaces. The depth map alone is not exported as a walkthrough.

## Pinned depth artifact

- Authors/original project: Lihe Yang and collaborators, https://github.com/DepthAnything/Depth-Anything-V2
- Small-model license: **Apache-2.0**. Larger Depth Anything V2 models have different licenses; this implementation does not select them.
- ONNX conversion project: https://github.com/fabio-sim/Depth-Anything-ONNX
- Conversion release: **v2.0.0**.
- Release asset: **depth_anything_v2_vits.onnx**.
- Expected size: **99,373,606 bytes**.
- SHA-256: **d2b11a11c1d4a12b47608fa65a17ee9a4c605b55ee1730c8e3b526304f2562be**.
- Runtime: **onnxruntime 1.22.1**, CPU execution; dependencies are pinned in `requirements-worker.txt`.

Run `python -m backend.download_model` after installing worker dependencies. The downloader uses verified HTTPS, checks the exact byte count and SHA-256, and atomically replaces the target only after verification. A checksum mismatch is a setup failure; do not disable verification or change the expected checksum to accept it. The default artifact is stored in `backend/models/`, which is ignored by Git and downloaded during the worker-image build. Ordinary website setup does not download this model.

Model setup needs outbound HTTPS access to `github.com` and the GitHub release-asset destination `release-assets.githubusercontent.com`. Python dependencies use the configured package index. Runtime inference uses the local model and does not send photos to a paid model provider. The website separately needs access to its configured worker origin.

## Other components and hardware

- **OpenCV 4.11.0.86** (`opencv-python-headless`): Apache-2.0 image/geometric methods; no separate object-generation weights or paid API are installed.
- **NumPy 2.2.6**: array processing (BSD-3-Clause).
- **ONNX Runtime**: MIT runtime, CPU inference.
- **Blender 3.4.1**, Debian Bookworm package `3.4.1+dfsg-2+b1`: GPL-3.0-or-later application, with its glTF exporter. The worker image installs it from signed Debian packages. Scene creation uses its bundled Python API; ordinary `pip install bpy` is not substituted for a verified Blender executable.
- **Three.js**: MIT browser renderer for the exported GLB, with embedded textures, source-camera alignment and modeled collision data.

The initial worker supports CPU-only execution. The portable Compose configuration allocates up to four CPU cores and 8 GB RAM and processes one job at a time. These are provisioning targets, not a claim that the existing Render web service has those resources. Keep depth inference and Blender off the small hosted web container. Use durable disk for source images, SQLite, scene JSON, textures, previews, GLBs and Blender files; allow space for multiple revisions and back up that volume. See [../DEPLOY.md](../DEPLOY.md) for worker deployment and exact settings.

## Limits of the model and reconstruction

Predictions are **relative inverse depth**, not measured distances. A single image does not establish a metric room scale, hidden surfaces, occluded cabinets, every material boundary or reliable object identity. The geometry stage infers supported room surfaces and major objects; it must reject images whose architecture is unsupported or ambiguous instead of substituting a sample room.

Texture regions originate from the uploaded image, but their unseen sides, material response and perspective rectification remain estimates. Reflections, vehicles, text, clutter and unusual architecture can be inaccurate. Source-camera comparison, confidence warnings and optional dimension/camera/object corrections are part of the workflow. Additional overlapping images or a spatial scan are necessary when accurate unseen geometry or measurements matter.

User photos and reconstruction artifacts are saved on the configured worker's durable volume so projects can be reopened. Review the owner-controlled retention and backup policy; the browser is not the only project store. Verify permission to process any input photos and retain upstream model/software license notices when distributing the worker.
