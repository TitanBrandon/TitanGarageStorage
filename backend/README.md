# Website and reconstruction worker

`backend.hosted` is the production website/API server. It preserves the existing shared HTTP Basic sign-in (`titan` and `SITE_PASSWORD`), protects project files, serves the frontend build, and proxies `/api/projects` to a separately provisioned worker. `GET /healthz` is its public liveness endpoint. The browser never receives the private worker token.

`backend.worker` owns the persistent SQLite project/job store and all source/generated files. One worker process leases one reconstruction at a time. The job analyzes the photo, writes a structured scene, runs the headless Blender builder, validates the actual exported artifacts, and then publishes the completed revision. Cancellation checks, process timeouts and job leases handle stopping and interrupted work. Completed revisions are kept when a corrected rebuild fails.

Use [../DEPLOY.md](../DEPLOY.md) for the portable Docker/Compose deployment and resource requirements. Keep the worker's `PROJECTS_DIR` and its SQLite database on the same persistent volume; do not use the ephemeral Render web filesystem for project storage. Back up the entire project directory. Starting several independent worker processes against one directory is unsupported; the provided worker command uses one process.

## Local worker on a provisioned machine

Use Python 3.12 and the pinned packages. Blender 3.4.1 from Debian Bookworm is the worker image's pinned system runtime; verify other Blender versions with actual exports before relying on them. Install Blender through the operating system's authenticated package manager, or build the provided worker image. No paid scene-generation service or API key is used.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-worker.txt
.venv/bin/python -m backend.download_model
```

Configure the worker's process environment without committing secret values:

- `WORKER_TOKEN`: private bearer token, matching the website setting.
- `PROJECTS_DIR`: durable writable project directory outside the repository.
- `BLENDER_BIN`: optional Blender executable; defaults to `blender`.
- `BLENDER_TIMEOUT_SECONDS`: Blender subprocess deadline; defaults to 1800 seconds.
- `ANALYSIS_TIMEOUT_SECONDS`: photo analysis subprocess deadline; defaults to 300 seconds.
- `OMP_NUM_THREADS`: cap CPU inference threads; the worker image sets 4.
- `OPENBLAS_NUM_THREADS`: the worker image sets 1 to avoid oversubscription.

Start a single authenticated local worker bound to loopback:

```sh
.venv/bin/python -m uvicorn backend.worker:app --host 127.0.0.1 --port 8012 --workers 1
```

The standalone `python -m backend.worker` entrypoint binds all interfaces for use inside its container. Do not use that binding to expose a worker directly on an untrusted network. Production remote access uses HTTPS, matching worker tokens and a durable volume as described in the deployment guide.

In a second process, configure the website's `WORKER_URL=http://127.0.0.1:8012`, matching `WORKER_TOKEN`, and `SITE_PASSWORD` of at least 16 characters. Install `backend/requirements-hosted.txt`, build the frontend, then run `npm run dev` or `python3.12 scripts/run_local.py`. The website launcher binds loopback and uses the production proxy/authentication path. TLS verification remains enabled for remote worker connections.

## Project API

All routes and asset downloads below are authenticated on the website. The web server adds its bearer token when proxying to the worker.

| Request | Result |
| --- | --- |
| `GET /api/projects/status` | Configuration, worker reachability and any setup requirement. |
| `GET /api/projects` | Persistent project summaries. |
| `POST /api/projects` | Multipart `photo`; promptly returns project ID, job ID and queued state. |
| `GET /api/projects/{id}` | State, real stage/progress, scene, corrections, warnings, revisions and artifact URLs. |
| `POST /api/projects/{id}/cancel` | Requests real worker-job cancellation. |
| `POST /api/projects/{id}/rebuild` | JSON corrections; queues a new revision. |
| `GET /api/projects/{id}/assets/{asset}` | Protected source, preview, GLB, Blender, scene JSON or manifest file. |

States are `queued`, `running`, `completed`, `failed` and `cancelled`. The worker reports actual stages including `analyzing`, `building` and `validating`. A completed revision supplies versioned asset URLs; loading/reloading the UI does not submit a new job. Browser localStorage stores only the selected project ID; it is not the project database.

Uploads accept JPG, PNG or WebP, at most 15 MB and 24 megapixels, with dimensions of at least 192 pixels per side. EXIF orientation is applied. The worker retains the normalized source and revision outputs in durable storage. Corrupt/unsupported images and failed Blender runs produce explicit error states.

Optional corrections use this structure; include only fields being changed:

```json
{
  "room": {"width": 6, "depth": 7, "height": 2.7},
  "camera": {"fov": 60, "position": [0, 1.6, 4], "target": [0, 1.2, -1]},
  "wall_corners": [[-3, -3.5], [3, -3.5], [3, 3.5], [-3, 3.5]],
  "objects": [{"id": "an-existing-scene-object-id", "position": [-2, 1, -3], "dimensions": [1, 2, 0.6]}]
}
```

Coordinates are metres in the Three.js room frame: X left/right, Y up, Z front/back. Object positions denote centres. Use IDs returned by the scene, not invented IDs. `camera.pitch` is also accepted in degrees. The backend validates bounds and polygon structure before applying corrections.

## Models, Blender and verification

[MODELS.md](MODELS.md) records model provenance and integrity. [BLENDER.md](BLENDER.md) documents real-mesh construction and material/export constraints. Inference is one input to geometric reconstruction; a depth map by itself is not the walkthrough. The browser loads the generated GLB and the separate source-camera/collision metadata.

```sh
.venv/bin/python -m unittest discover -s backend -p 'test_*.py' -v
npm run build
npm test
```

Use separate durable storage for integration-test projects. Actual quality validation requires permitted interior photos processed through image analysis and Blender, then inspection of the exported GLBs in the browser. Mocked queues, installation checks or standalone preview renders do not establish an accurate interactive reconstruction. Inspect source alignment, hidden-surface estimates, textured object sides, additional viewpoints and collisions, and report remaining mismatches.
