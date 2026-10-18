# Titan Space Studio

A first experiment for Titan Garage Storage: upload one photo, estimate its visible depth using **Depth Anything V2 Small**, then explore that textured surface with a Three.js viewer. No Canva, Blender, paid inference service or API key is needed.

The initial covered showroom is a separately authored 3D sample inspired by the reference photo. It demonstrates navigation; it is clearly marked as a sample. Select your actual image in the upload panel to reconstruct that image.

## Try the Windows download

[**Download Space Studio for Windows**](https://github.com/TitanBrandon/TitanGarageStorage/raw/refs/heads/main/downloads/Titan-Space-Studio-Windows.zip)

The packaged ZIP includes the built frontend, so it needs Python 3.12 but does not need Node.js. Install Python 3.12, extract the entire ZIP, and double-click **Start Windows.bat**. The launcher installs its dependencies in an ignored local `.venv`, downloads the checksum-verified model, starts the app, and opens your browser. Keep the terminal window open while using it. See **START HERE.txt**. For a source checkout, build the frontend first using the setup instructions below.

## Start in this prepared cloud environment

From `/workspace/TitanGarageStorage`:

```sh
npm run dev
```

This starts the Python inference service, checks model readiness, and starts Vite. Stop both with Ctrl+C. If the backend is already running, use `npm run dev:ui` to start just the frontend.

Upload a JPG, PNG or WebP (15 MB maximum, at least 128 × 128 pixels, up to 24 megapixels), then select **Create 3D view**. Switch between Orbit and Walk through, and compare the textured surface with its point cloud.

- **Orbit:** drag to rotate, scroll/pinch to move closer, right-drag to pan.
- **Walk through:** click the canvas, move with W/A/S/D or arrow keys, look with the mouse. Escape releases the mouse. Q/E moves vertically in a photo reconstruction.
- **Touch:** drag to look around and hold the on-screen arrows to move.
- **Reset view:** return to the original viewpoint.

## Set up a fresh machine

Requires Node.js 22.12+ (Node 24 tested), Python 3.12 and a WebGL-capable browser. From the checkout root:

```sh
bash scripts/setup.sh
npm run dev
```

Setup creates an ignored `.venv`, installs pinned Python packages and npm lockfile dependencies, downloads the checksum-verified 99 MB model, and builds the frontend. On Windows, create `.venv` using `python -m venv .venv`, install `backend/requirements.txt`, run `python -m backend.download_model` using that venv, then `npm ci` and `npm run dev`.

The cloud snapshot uses `/workspace/.titan-venv`; the startup script detects it. Set `TITAN_PYTHON` to use a different Python executable. The backend binds to loopback; Vite forwards `/api` to it. Uploaded photos are processed on this server and are not sent to a third-party model service. The application does not save uploads in a photo library. Model details and license: [backend/MODELS.md](backend/MODELS.md).

## Validate

```sh
npm run build
/workspace/.titan-venv/bin/python -m unittest backend.test_api -v
# Keep the backend running for the real inference browser test:
npm test
```

For another machine, use `.venv/bin/python` instead. Playwright uses system Chromium when available, or its own installation (`npx playwright install chromium`). Browser checks cover sample navigation, genuine upload/inference, point-cloud switching, input and backend errors, and mobile layout. API checks exercise actual CPU inference, EXIF rotation, invalid files, size limits and concurrency limits.

## What this prototype reconstructs

A single photo contains only one viewpoint. The model predicts **relative depth**, and the viewer projects the photo into an approximate mesh. It does not recover metric measurements, hidden surfaces, the backs of cars, or areas outside the photograph. Moving far away from the original camera reveals holes or distortion. The viewer leaves missing surfaces empty rather than presenting guessed content as captured geometry.

This is a useful first interaction and depth experiment. A complete, realistic room walkthrough needs a separate reconstruction workflow using overlapping photographs, video or a spatial scan. This development prototype is not configured for public hosting, accounts, persistent storage or multi-user operation. The production frontend build needs an API reverse proxy when deployed; Vite preview alone does not proxy the Python service.

Cloud tasks already provide isolated workspaces. Use the existing checkout; creating another Git worktree is unnecessary.
