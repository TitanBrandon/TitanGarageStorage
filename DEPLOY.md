# Deploy the Blender reconstruction workflow

Keep **https://titan-space-studio.onrender.com/** and the existing Render service
**`srv-dba8m4ss728c738gk3ng`**. Its lightweight Python server serves the browser
app, preserves the `titan`/`SITE_PASSWORD` login, and proxies private project
requests to a separate reconstruction worker. The worker runs local analysis,
the pinned depth model, and headless Blender, with projects on persistent disk.
No scene-generation API key or per-generation service is used.

The Render web image deliberately does not install Blender or load the depth
model. `render.yaml` requests a Free web service; this is a configuration default,
**not verification of the existing service's actual plan, memory, or CPU**.
There were no Render API credentials available to inspect that service, and this
development environment blocked outbound access to the live site and Render
documentation. Check its **Instance Type** page for actual resources. Do not
assume a small web instance can run reconstruction. The CPU worker needs no GPU.

## 1. Provide an existing worker host and durable storage

Use an available Linux server or Linux Docker host with Docker Engine and
Compose v2. Start with **4 CPU cores, 8 GB RAM, and 20 GB free persistent disk**,
growing with saved projects. These are provisioning targets; actual usage and
processing time depend on the image and retained revisions. Installation needs
Debian repositories, the Python index, and the pinned GitHub model release.
Inference and Blender do not call an external model provider after installation.

The worker also needs a stable HTTPS address reachable from Render. A private
`localhost` server on your computer is not reachable from Render. Use an existing
trusted reverse proxy or the optional Caddy TLS service below. This project does
not buy compute, upgrade a plan, or create a storage service. If no suitable host
exists, provide that compute and persistent disk before enabling hosted uploads.

On the worker host, obtain this repository and create an ignored **`.env.worker`**
file in its root. Generate a long random token in your password manager and set:

```dotenv
WORKER_TOKEN=replace-with-a-long-random-secret
WORKER_DOMAIN=worker.your-real-domain.example
```

Use a real domain you control. Point its DNS to this server and permit inbound
TCP 80/443 if using Caddy. Keep the same `WORKER_TOKEN` for Render's secure
environment settings. Never commit it or include it in browser code or URLs.

```sh
docker compose --env-file .env.worker -f docker-compose.worker.yml build worker
docker compose --env-file .env.worker -f docker-compose.worker.yml --profile https up -d
```

For an existing HTTPS reverse proxy, omit `--profile https` and proxy to
`http://127.0.0.1:8012`, preserving Authorization headers. The direct worker port
binds to loopback. Caddy's optional profile obtains TLS certificates and proxies
to `worker:8012`. The worker requires its bearer token for project data and
generated artifacts even behind HTTPS. Do not expose its files as public static
downloads.

The image installs **Blender `3.4.1+dfsg-2+b1`** from Debian Bookworm's signed
repository; this candidate was checked in an actual Bookworm container.
`backend/requirements-worker.txt` pins ONNX Runtime, NumPy, OpenCV, Pillow, and the
API dependencies. The build downloads the existing Depth Anything V2 Small ONNX
release and checks its fixed byte count and SHA-256. No model download is needed
at runtime. See [model provenance and license](backend/MODELS.md).

The worker runs as UID/GID **10001:10001**. Compose mounts the named
**`titan_projects`** volume at `/data`; `PROJECTS_DIR=/data/projects` contains
`projects.sqlite3`, uploads, scene descriptions, per-revision textures, previews,
GLBs, and editable Blender files. Preserve this volume when replacing containers.
For a bind mount or an existing persistent disk, give UID 10001 write access and
mount it at `/data`. Production projects must not live on ephemeral container or
Render web storage.

## 2. Connect the existing Render website

After this code reaches the existing repository's `main` branch:

1. Open [the existing service's Environment settings](https://dashboard.render.com/web/srv-dba8m4ss728c738gk3ng/env).
2. Keep **`SITE_PASSWORD`**. Username remains **`titan`**. The production server
   requires at least 16 password characters; securely replace an older short
   password if needed.
3. Add **`WORKER_URL=https://your-actual-worker-domain`** and **`WORKER_TOKEN`**
   with the same secret used by the worker. Do not append `/api/projects` to the
   URL.
4. Remove unused `WORLDLABS_API_KEY`/`WLT_API_KEY` bindings when selecting the new
   code. Blender reconstruction does not require them.
5. Save settings, then use **Manual Deploy → Deploy latest commit** on this same
   Render service. Preserve its URL and health check **`/healthz`**. Do not create
   a duplicate website or a new paid worker through a Blueprint.
6. Open **https://titan-space-studio.onrender.com/**, sign in, and check worker
   availability before uploading.

The Blueprint's `SITE_PASSWORD: generateValue: true` is for initial service
creation; it does not instruct you to replace this website's current password.
Use the existing dashboard settings above. Automatic deployment stays disabled.

Public worker addresses must use HTTPS. HTTP on a trusted private Docker network
requires **`WORKER_ALLOW_HTTP=1`** on the web process; never enable that exception
for an internet-facing worker. Localhost HTTP is supported for local testing.

## 3. Use and operate the site

Upload a permitted garage/interior photo and select **Create 3D walkthrough**.
The app creates a durable project and reports its real processing stages. Open
the completed walkthrough, compare the source-camera preview with the upload,
and download its GLB or Blender project. Reloading reconnects to saved projects;
the worker's database and disk are the project store, rather than browser data.

The default worker processes one reconstruction at a time, bounds its queue, and
gives photo analysis a 300-second time limit (`ANALYSIS_TIMEOUT_SECONDS`) and
Blender an 1800-second time limit (`BLENDER_TIMEOUT_SECONDS`).
Leave the worker host running during jobs. Use the in-app cancellation control
when needed. Inspect failures with:

```sh
docker compose --env-file .env.worker -f docker-compose.worker.yml logs --tail=100 worker
```

Update on the same host with the same Compose project and persistent volume:

```sh
git pull --ff-only
docker compose --env-file .env.worker -f docker-compose.worker.yml build worker
docker compose --env-file .env.worker -f docker-compose.worker.yml --profile https up -d
```

Back up the **whole `/data/projects` directory**, including the SQLite database,
WAL files, and all project assets, to independent durable storage. Stop the
worker for a simple consistent filesystem backup, or use SQLite's supported
online backup with matching assets. Do not delete the volume during updates.
Monitor disk capacity and use your own retention policy for saved projects.

The shared login lets its users access this site's projects and worker capacity;
this personal deployment has no separate customer accounts. Uploaded photos stay
on your worker's disk, so protect that disk and its backups.

## Validation and limits

Both the web server and worker must be connected before the public site can
generate scenes. A successful build or web health check alone does not establish
that the hosted path works. After connection, test a real upload, completed
Blender export, textured walkthrough, page reload, and protected GLB/Blender
downloads.

One photo cannot determine exact dimensions or hidden surfaces. Automatic room,
opening, object, and material estimates can be wrong; inspect the comparison and
use corrections. Unsupported or ambiguous photos should request correction or
fail. This workflow does not promise a photographically exact scan from one image.

Blender is GPL software; Depth Anything V2 Small is Apache-2.0 licensed. Keep
model provenance and dependency notices with distributions, and use photos you
have permission to process.
