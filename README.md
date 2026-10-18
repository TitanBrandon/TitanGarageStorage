# Titan Space Studio

Upload a real photo, generate an explorable scene using the World Labs Marble API, and walk through its Gaussian-splat output in a Three.js/Spark viewer. This replaces the original cartoon showroom and limited photo-depth mesh. No sample geometry is presented as a reconstruction of your photo.

**A provider API key and API credits are required to generate a world.** The integration cannot be described as live-validated until it successfully generates a world with an authorized account. Local exported SPZ/PLY/SPLAT scenes can be imported without an API key.

## Try the Windows download

[**Download Space Studio v0.2 for Windows**](https://github.com/TitanBrandon/TitanGarageStorage/raw/refs/heads/main/downloads/Titan-Space-Studio-Windows-v0.2.zip)

Install Python 3.12, extract the entire ZIP, and double-click **Start Windows.bat**. The download contains the built frontend, so it does not need Node.js. On first launch it installs Python dependencies and asks for a World Labs API key in the terminal. Typing/pasting the key is hidden. The key is retained only in memory for that session. Press Enter without a key to import an existing scene instead.

Create a World Labs API account, credits and key at https://platform.worldlabs.ai/ . API access and API credits may differ from consumer Marble subscriptions; consult your account for eligibility and current pricing. Keep the terminal window open while using the app. **START HERE.txt** contains the full steps.

## Development

Requires Node.js 22.12+ (Node 24 tested), Python 3.12 and a browser with WebGL2.

```sh
bash scripts/setup.sh
# Configure WORLDLABS_API_KEY in your process or secure environment settings.
npm run dev
```

The cloud snapshot uses `/workspace/.titan-venv`; startup detects it. For another venv, set `TITAN_PYTHON` to its Python executable. The Python API binds to loopback on 8000 and Vite forwards `/api` from 5173. Startup waits for the app server, but provider availability and credentials are checked separately in the UI. Stop both with Ctrl+C. If this project's API is already running, use `npm run dev:ui` for just the frontend.

For the Python-only packaged app, `scripts/run_local.py` serves the built frontend and API together. In a source checkout, build first with `npm run build`.

## Generate and explore

1. Connect a World Labs API account with credits. Keep `WORLDLABS_API_KEY` server-side; `WLT_API_KEY` is also accepted.
2. Select a JPG/PNG/WebP photo (15 MB maximum, at least 128 pixels per side, up to 24 megapixels).
3. Select quick preview (`Marble 0.1-mini`) or quality (`Marble 0.1-plus`) and submit the generation once. Each accepted request uses provider credits. Your photo is sent to World Labs.
4. Wait for the provider operation. The app polls the existing operation and preserves its ID across reloads; it never resubmits a paid generation automatically. Stopping polling does not cancel provider generation or reverse its charges.
5. Once the scene asset is ready, use Orbit or Walk through. If the browser cannot load the asset, the provider's own Marble viewer link remains available when returned.

Mouse: drag to look; in walk mode use W/A/S/D or arrow keys and Escape to release the mouse. Touch: drag to look and hold the on-screen movement arrows. Reset returns to the initial viewpoint. Local scene import also accepts an exported SPZ, PLY or SPLAT file.

## What realistic means

Gaussian splats can preserve a realistic photographic appearance. One-photo world generation still invents surfaces and areas outside the original viewpoint. Cars, lettering, layout, lighting and proportions may change. This is a visual concept, not a measured reconstruction. For a faithful walkthrough of the actual property, capture overlapping photos or a slow video/spatial scan and reconstruct those observations instead.

The viewer supports free navigation; without a verified collider mesh it does not guarantee wall/car collision or an accurately grounded walking height. We do not claim exact physical scale.

## Network and credentials

Generation calls `https://api.worldlabs.ai/marble/v1` using a server-side `WLT-Api-Key` header. The app accepts a runtime `WORLDLABS_API_KEY` or `WLT_API_KEY`. Cloud environment settings declare the secure key and network access for `api.worldlabs.ai` / `*.worldlabs.ai`. Generated asset URLs may use additional provider destinations; add only observed required hosts if a real response identifies them. Do not disable TLS verification.

The API key is never sent to the frontend. Unlike the earlier local-depth experiment, generation sends the uploaded photo to an external service; review the provider's terms for retention and usage. The app does not retain a photo library. This is a local development prototype without public user accounts or public API authentication. Public hosting needs a separate deployment and authentication setup.

## Validation

```sh
npm run build
/workspace/.titan-venv/bin/python -m unittest backend.test_worlds -v
# Keep the backend running for browser checks:
npm test
```

Use `.venv/bin/python` on another machine. Browser checks use system Chromium if available, or Playwright Chromium (`npx playwright install chromium`). Mocked provider checks verify the integration contract and errors; they do not prove provider generation quality or live account access. A real splat import validates rendering independently of a paid generation. No paid provider request is made by the automated tests.

## Official references

- [World Labs image generation example](https://github.com/worldlabsai/worldlabs-api-examples/blob/main/generate-world-from-image.py)
- [World Labs API models](https://github.com/worldlabsai/worldlabs-api-python/blob/main/src/worldlabs_api/models.py)
- [World Labs viewer example](https://github.com/worldlabsai/worldlabs-api-examples/blob/main/web-generate-world/index.html)
- [Spark viewer](https://github.com/sparkjsdev/spark)

The earlier local Depth Anything endpoint remains available for comparison. Its optional model downloader, license and limitations are documented in backend/MODELS.md; it is not the realistic generation workflow and setup no longer downloads that model.

Cloud tasks already provide isolated workspaces. Use the existing checkout; do not create a Git worktree unless the user explicitly requests it.
