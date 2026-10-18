# Titan Space Studio

Photo-guided reconstruction of garages and interiors, using a local depth model, geometric image analysis, headless Blender, and a Three.js GLB walkthrough. Each project stores its source image, structured scene description, source-camera preview, editable `.blend`, and textured `.glb` on a persistent reconstruction worker. The website retains Titan branding and its shared sign-in.

No paid scene-generation API or provider API key is required. The reconstruction worker supplies the compute and storage; it is separate from the lightweight website. See [DEPLOY.md](DEPLOY.md) for the deployment contract and resource requirements. The existing website address is **https://titan-space-studio.onrender.com/**; new features require deployment of this code and connection of the worker.

## Use the website

1. Open the existing site and sign in as **titan** with your site password.
2. Choose a clear garage or interior photo, then click **Create 3D walkthrough**. Measurements are optional. JPG, PNG and WebP are accepted, up to 15 MB and 24 megapixels, with at least 192 pixels per side.
3. Follow the worker's actual analysis, Blender build and validation stages. Reloading reconnects to the saved project. **Cancel reconstruction** requests cancellation of that worker job.
4. Use **Compare photo** for the original beside the matched source camera. **Blender preview** displays the generated preview render; it is distinct from the interactive model.
5. Use **Orbit**, or **Walk through** with mouse/WASD or arrow keys. On touch screens, drag to look and hold the movement buttons. Walking uses a grounded eye height and collision against the modeled room and supported major objects. Press Escape to release the mouse.
6. Review the confidence notes. Optionally correct dimensions, camera alignment, wall corners or object positions, then rebuild. The previous completed revision remains available while the new one processes.
7. Reopen a project from **Saved spaces**, or download its GLB, Blender project, scene JSON and preview.

If the website says **Reconstruction worker needed**, its web server is running but reconstruction is not configured. Follow [DEPLOY.md](DEPLOY.md); the app will not substitute a sample room. The previous Windows ZIP packages have been retired because they contain the superseded workflow. Normal website use does not require Python, Blender or a ZIP on the user's computer.

## What one photo can establish

The source image drives the inferred camera, room surfaces, supported major objects, colors and material textures. Blender constructs real meshes with side surfaces and exports embedded textures. A depth map alone is not the finished scene.

One view leaves room dimensions, hidden surfaces, occluded objects and ambiguous boundaries uncertain. The first implementation prioritizes garages and interiors with visible architectural lines and floor space. It does not provide a measured scan, guarantee exact object recognition, or establish the backs of objects. Detailed clutter, reflective vehicles, lettering and unusual architecture can remain inaccurate or unsupported. Review each project's warnings and source comparison before relying on the result. Unsupported inputs should report a failure, not a successful generic scene.

## Development website

Requires Node.js 22.12+ (Node 24 supported), Python 3.12, and a browser with hardware-accelerated WebGL. Work in the existing checkout; cloud tasks are already isolated, so do not create a Git worktree unless explicitly requested.

```sh
bash scripts/setup.sh
```

Configure these process environment variables using your shell or secure environment settings, without committing their values:

- `SITE_PASSWORD`: at least 16 characters; the browser signs in as `titan`.
- `WORKER_URL`: worker origin, for example `http://127.0.0.1:8012` for a local worker, or its HTTPS origin in production.
- `WORKER_TOKEN`: the same private bearer token configured on the worker.
- `TITAN_PYTHON`: optional Python executable; startup otherwise detects `.venv` and the cloud `/workspace/.titan-venv`.

```sh
npm run dev
```

The authenticated website API runs on loopback port 8000; Vite on loopback 5173 forwards `/api`. Sign in with the same site credentials for protected API requests. The script starts the production `backend.hosted` API, not a different generation backend. `TITAN_UI_HOST` can explicitly change the Vite binding for a trusted preview environment. Stop the website with Ctrl+C. It does not stop the separately managed worker or delete saved projects.

`scripts/setup.sh` installs only the lightweight web dependencies and frontend build by default. It does not install Blender, download the depth model, start a worker, or expose a worker to the network. A real worker is required for reconstruction; missing worker configuration is reported in the UI.

## Run a worker

The portable supported path is the worker Docker image and persistent Compose volume in [DEPLOY.md](DEPLOY.md). Reconstruction uses CPU inference and headless Blender; no GPU is required for the initial pipeline. Provision the worker independently of the Render web container and preserve its project volume, including SQLite and artifacts.

For an already provisioned local machine with Blender installed, see [backend/README.md](backend/README.md). `bash scripts/setup.sh --worker` installs pinned worker Python packages and downloads the checksum-verified depth model. It checks for Blender but does not install the system package. Start exactly one worker process and set `PROJECTS_DIR` to a persistent location outside the checkout. The documented local command binds the worker to loopback and retains bearer authentication.

To serve an existing frontend build without Vite:

```sh
npm run build
python3.12 scripts/run_local.py
```

This launcher uses the same `SITE_PASSWORD`, `WORKER_URL` and `WORKER_TOKEN` settings. It serves the production-style authenticated website on loopback, opens the browser when ready, and does not ask for a paid API key or launch an unauthenticated remote worker.

## Backend and validation

- [Backend workflow and API](backend/README.md)
- [Model provenance, license and download integrity](backend/MODELS.md)
- [Blender scene construction](backend/BLENDER.md)
- [Render and worker deployment](DEPLOY.md)
- [Actual photo results, browser evidence and fidelity limits](validation/README.md)

```sh
npm run build
.venv/bin/python -m unittest discover -s backend -p 'test_*.py' -v
npm test
```

Use the configured venv's Python path on other machines. Browser checks require Chromium, available through system Chromium or `npx playwright install chromium`. Tests that exercise reconstruction need the real worker, model and Blender runtime, with a separate test project directory. A frontend build, mocked API check or imported prebuilt GLB does not establish reconstruction quality. Actual photo-to-model checks must inspect the generated preview, textured browser model, additional viewpoints and collision, and report input-specific limitations.

The public `/healthz` endpoint checks website liveness. Project requests and uploaded/generated assets stay behind the existing site authentication; the browser accesses them through same-origin URLs. The server forwards requests to the worker with its private token. Runtime reconstruction does not call an external scene-generation provider. Retention and backups are controlled by the owner of the worker's durable project storage.
