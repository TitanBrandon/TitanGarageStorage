"""Portable, authenticated reconstruction worker with a persistent SQLite queue."""

from contextlib import asynccontextmanager
import hmac
import hashlib
import importlib.util
import io
import json
import logging
import math
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid
import warnings

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from backend.limits import MAX_UPLOAD_BYTES, RequestLimits
from backend.project_store import ProjectStore, StoreError

LOGGER = logging.getLogger("titan.worker")
ROOT = Path(__file__).resolve().parents[1]
ASSETS = {"source", "preview", "glb", "blend", "scene", "manifest"}
_model_check = {}


def runtime_status():
    from backend.model import MODEL_PATH, MODEL_SHA256
    missing = []
    if not shutil.which(os.environ.get("BLENDER_BIN", "blender")):
        missing.append("Blender executable")
    for module in ("onnxruntime", "numpy", "cv2", "backend.reconstruction"):
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    try:
        stat = MODEL_PATH.stat()
        fingerprint = (str(MODEL_PATH), stat.st_size, stat.st_mtime_ns)
        if fingerprint not in _model_check:
            with MODEL_PATH.open("rb") as model:
                _model_check.clear()
                _model_check[fingerprint] = hashlib.file_digest(model, "sha256").hexdigest() == MODEL_SHA256
        if not _model_check[fingerprint]:
            missing.append("verified depth model (checksum mismatch)")
    except OSError:
        missing.append("verified depth model")
    return {"configured": True, "workerReachable": True, "setupRequired": bool(missing), "ready": not missing, "missing": missing, "storage": "PROJECTS_DIR", "message": "Install the worker runtime prerequisites: " + ", ".join(missing) if missing else "Blender reconstruction worker is ready."}


class JobCancelled(Exception):
    pass


def normalize_photo(data):
    if not data:
        raise StoreError(422, "Choose a garage or interior photo first.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise StoreError(413, "Choose an image smaller than 15 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"}:
                    raise StoreError(415, "Upload a JPG, PNG, or WebP image.")
                if original.width * original.height > 24_000_000:
                    raise StoreError(413, "Choose an image with fewer than 24 million pixels.")
                if min(original.size) < 192:
                    raise StoreError(422, "Use a photo at least 192 pixels in each direction.")
                original.load()
                image = ImageOps.exif_transpose(original).convert("RGB")
                image.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, "JPEG", quality=95)
                return output.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise StoreError(413, "Choose an image with fewer than 24 million pixels.") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise StoreError(422, "This photo could not be read. Try a JPG, PNG, or WebP image.") from None


def validate_corrections(value):
    if not isinstance(value, dict) or len(json.dumps(value)) > 65536:
        raise StoreError(422, "Corrections must be a small JSON object.")
    if set(value) - {"room", "camera", "wall_corners", "objects"}:
        raise StoreError(422, "Unknown correction field.")

    def number(item, lower=-100, upper=100):
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or not lower <= item <= upper:
            raise StoreError(422, "Correction values must be finite and within supported room dimensions.")

    def vector(item, length=3, positive=False):
        if not isinstance(item, list) or len(item) != length:
            raise StoreError(422, "Correction coordinates have an invalid shape.")
        for component in item:
            number(component, 0.02 if positive else -100, 50 if positive else 100)

    if "room" in value:
        room = value["room"]
        if not isinstance(room, dict) or set(room) - {"width", "depth", "height"}:
            raise StoreError(422, "Unknown room correction field.")
        for key, component in room.items():
            number(component, 1.8 if key == "height" else 1, 12 if key == "height" else 50)
    if "camera" in value:
        camera = value["camera"]
        if not isinstance(camera, dict) or set(camera) - {"position", "target", "fov", "pitch"}:
            raise StoreError(422, "Unknown camera correction field.")
        for key, component in camera.items():
            if key in {"position", "target"}:
                vector(component)
            else:
                number(component, 20 if key == "fov" else -89, 120 if key == "fov" else 89)
    if "wall_corners" in value:
        corners = value["wall_corners"]
        if not isinstance(corners, list) or not 3 <= len(corners) <= 12:
            raise StoreError(422, "Provide 3 to 12 room corners.")
        for corner in corners:
            vector(corner, length=2)
    if "objects" in value:
        objects = value["objects"]
        if not isinstance(objects, list) or len(objects) > 100:
            raise StoreError(422, "Too many object corrections.")
        for obj in objects:
            if not isinstance(obj, dict) or set(obj) - {"id", "position", "dimensions"} or not isinstance(obj.get("id"), str) or len(obj["id"]) > 100:
                raise StoreError(422, "Object corrections need a valid object ID.")
            for key in ("position", "dimensions"):
                if key in obj:
                    vector(obj[key], positive=key == "dimensions")
    return value


def validate_outputs(directory):
    """Check actual binary formats, embedded glTF resources and modeled geometry."""
    glb = (directory / "scene.glb").read_bytes()
    if len(glb) < 24:
        raise RuntimeError("Blender produced an incomplete GLB file.")
    magic, version, length = struct.unpack_from("<4sII", glb)
    if magic != b"glTF" or version != 2 or length != len(glb):
        raise RuntimeError("Blender produced an invalid GLB header.")
    json_length, json_type = struct.unpack_from("<I4s", glb, 12)
    if json_type != b"JSON" or 20 + json_length > len(glb):
        raise RuntimeError("The GLB contains an invalid scene chunk.")
    document = json.loads(glb[20:20 + json_length])
    if not document.get("meshes") or not document.get("nodes"):
        raise RuntimeError("The exported walkthrough has no modeled geometry.")
    images = document.get("images", [])
    if not images:
        raise RuntimeError("The exported walkthrough contains no photo-derived textures.")
    for image in images:
        if "bufferView" not in image and not str(image.get("uri", "")).startswith("data:"):
            raise RuntimeError("The GLB depends on an external texture instead of embedding it.")
    if any("uri" in buffer and not str(buffer["uri"]).startswith("data:") for buffer in document.get("buffers", [])):
        raise RuntimeError("The GLB depends on an external mesh buffer.")
    with (directory / "scene.blend").open("rb") as blend:
        if blend.read(7) != b"BLENDER":
            raise RuntimeError("The editable Blender project is invalid.")
    with Image.open(directory / "preview.png") as preview:
        if preview.format != "PNG" or min(preview.size) < 64:
            raise RuntimeError("The Blender preview is invalid.")
        preview.verify()
    manifest = json.loads((directory / "manifest.json").read_text())
    mesh_count = manifest.get("mesh_count", manifest.get("meshCount", manifest.get("object_count", 0)))
    if not isinstance(mesh_count, (int, float)) or mesh_count < 1:
        raise RuntimeError("Blender did not report any exported meshes.")
    validation = {"glbVersion": version, "meshes": len(document["meshes"]), "embeddedImages": len(images), "validatedAt": time.time()}
    (directory / "validated.json").write_text(json.dumps(validation))
    return validation


class WorkerRunner:
    def __init__(self, store):
        self.store, self.owner = store, str(uuid.uuid4())
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.loop, name="titan-project-worker", daemon=True)
        self.process = None

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.kill_process()
        self.thread.join(timeout=15)

    def kill_process(self):
        process = self.process
        if process is None or process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)
        except ProcessLookupError:
            pass

    def loop(self):
        while not self.stop_event.is_set():
            try:
                job = self.store.lease_next(self.owner)
                if job:
                    self.run(job)
                    continue
            except Exception:
                LOGGER.exception("Worker queue error")
            self.stop_event.wait(0.5)

    def run(self, job):
        heartbeat_done = threading.Event()

        def heartbeat():
            while not heartbeat_done.wait(10):
                self.store.heartbeat(job["id"], self.owner)

        monitor = threading.Thread(target=heartbeat, daemon=True)
        monitor.start()
        directory = self.store.revision_directory(job["project_id"], job["revision"])
        # Reclaimed jobs rebuild their unpublished revision from the original photo.
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)

        def cancelled():
            return self.stop_event.is_set() or self.store.is_cancelled(job["id"])

        def progress(*args, **kwargs):
            if cancelled():
                raise JobCancelled()
            percentage = next((arg for arg in args if isinstance(arg, (int, float))), kwargs.get("progress", 20))
            percentage = percentage * 100 if 0 <= percentage <= 1 else percentage
            self.store.progress(job["id"], "analyzing", min(48, max(3, percentage * 0.48)))

        try:
            if cancelled():
                raise JobCancelled()
            scene_path = directory / "scene.json"
            corrections_path = directory / "corrections.json"
            corrections_path.write_text(json.dumps(job["corrections"]))
            analyze_command = [sys.executable, "-m", "backend.worker", "--analyze", str(self.store.directory(job["project_id"]) / "source.jpg"), str(directory), str(corrections_path)]
            self.run_subprocess(analyze_command, job, directory, cancelled, "analyzing", max(15, min(3600, int(os.environ.get("ANALYSIS_TIMEOUT_SECONDS", "300")))))
            if cancelled():
                raise JobCancelled()
            self.store.progress(job["id"], "building", 52)
            self.build(job, scene_path, directory, cancelled)
            if cancelled():
                raise JobCancelled()
            self.store.progress(job["id"], "validating", 94)
            validate_outputs(directory)
            if cancelled():
                raise JobCancelled()
            self.store.finish(job, "completed")
        except JobCancelled:
            if self.stop_event.is_set() and not self.store.is_cancelled(job["id"]):
                self.store.requeue(job)
            else:
                self.store.finish(job, "cancelled")
        except Exception as error:
            LOGGER.exception("Reconstruction failed for project %s", job["project_id"])
            message = str(error)[:700] or "Reconstruction failed. Try another interior photo."
            if self.stop_event.is_set() and not self.store.is_cancelled(job["id"]):
                self.store.requeue(job)
            else:
                self.store.finish(job, "cancelled" if cancelled() else "failed", message if not cancelled() else None)
        finally:
            self.kill_process()
            self.process = None
            heartbeat_done.set()
            monitor.join(timeout=1)

    def build(self, job, scene_path, directory, cancelled):
        binary = os.environ.get("BLENDER_BIN", "blender")
        if not shutil.which(binary):
            raise RuntimeError("Blender is not installed on this worker. Install the worker runtime before reconstructing photos.")
        timeout = max(30, min(7200, int(os.environ.get("BLENDER_TIMEOUT_SECONDS", "1800"))))
        command = [binary, "--background", "--threads", str(min(4, os.cpu_count() or 1)), "--python", str(ROOT / "backend/blender_build.py"), "--", "--scene", str(scene_path), "--output", str(directory)]
        self.run_subprocess(command, job, directory, cancelled, "building", timeout)

    def run_subprocess(self, command, job, directory, cancelled, phase, timeout):
        log_path = directory / ("analysis.log" if phase == "analyzing" else "blender.log")
        with log_path.open("wb") as log, log_path.open("r", errors="replace") as progress_log:
            self.process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name == "posix")
            started = time.monotonic()
            last_stage, last_progress, diagnostic = phase, 2 if phase == "analyzing" else 52, None
            while self.process.poll() is None:
                if cancelled():
                    self.kill_process()
                    raise JobCancelled()
                if time.monotonic() - started > timeout:
                    self.kill_process()
                    raise RuntimeError(("Photo analysis" if phase == "analyzing" else "Blender") + " exceeded the processing time limit. Try a simpler interior photo or a better provisioned worker.")
                for line in progress_log.readlines():
                    try:
                        event = json.loads(line)
                        if phase == "building" and event.get("stage") in {"building_geometry", "exporting_glb", "rendering_preview"}:
                            last_stage = event["stage"]
                            last_progress = {"building_geometry": 57, "exporting_glb": 73, "rendering_preview": 82}[last_stage]
                        elif phase == "analyzing" and event.get("stage") == "analyzing":
                            last_progress = max(3, min(48, float(event.get("progress", 20)) * 0.48))
                        if event.get("stage") == "failed":
                            diagnostic = str(event.get("message", ""))[:500]
                    except (ValueError, TypeError, AttributeError):
                        pass
                self.store.progress(job["id"], last_stage, last_progress)
                self.stop_event.wait(0.5)
            if self.process.returncode != 0:
                remaining = progress_log.read()
                for line in remaining.splitlines():
                    try:
                        event = json.loads(line)
                        if event.get("stage") == "failed":
                            diagnostic = str(event.get("message", event.get("error", "")))[:500]
                    except (ValueError, AttributeError):
                        pass
                raise RuntimeError(diagnostic or ("Photo analysis could not identify a supported interior. Try a clearer garage or room photo." if phase == "analyzing" else "Blender could not construct this scene. Review the worker log and correct the room layout."))


class WorkerAuthentication:
    def __init__(self, app, token=None):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/healthz":
            return await self.app(scope, receive, send)
        token = self.token or os.environ.get("WORKER_TOKEN", "")
        received = dict(scope.get("headers", [])).get(b"authorization", b"")
        expected = ("Bearer " + token).encode()
        if not token or not hmac.compare_digest(received, expected):
            return await JSONResponse({"detail": "Worker authentication required."}, 401)(scope, receive, send)
        return await self.app(scope, receive, send)


def create_app(projects_dir=None, *, start_runner=True, token=None):
    @asynccontextmanager
    async def lifespan(app):
        configured = projects_dir or os.environ.get("PROJECTS_DIR")
        if not configured or not Path(configured).is_absolute():
            raise RuntimeError("Set PROJECTS_DIR to an absolute directory on a persistent worker volume.")
        if not (token or os.environ.get("WORKER_TOKEN")):
            raise RuntimeError("Set WORKER_TOKEN before starting the reconstruction worker.")
        app.state.store = ProjectStore(Path(configured))
        app.state.runner = WorkerRunner(app.state.store)
        if start_runner:
            app.state.runner.start()
        yield
        if start_runner:
            app.state.runner.stop()

    app = FastAPI(title="Titan reconstruction worker", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestLimits)
    app.add_middleware(WorkerAuthentication, token=token)

    @app.exception_handler(StoreError)
    async def store_error(request, error):
        return JSONResponse({"detail": error.message}, error.status)

    @app.get("/healthz")
    def health():
        return {"ready": True}

    @app.get("/api/projects/status")
    def status():
        return runtime_status()

    @app.get("/api/projects")
    def projects():
        return {"projects": app.state.store.list()}

    @app.post("/api/projects", status_code=202)
    async def upload(photo: UploadFile):
        try:
            data = await photo.read(MAX_UPLOAD_BYTES + 1)
            name = Path((photo.filename or "Uploaded room").replace("\\", "/")).stem
            name = "".join(character for character in name if character.isprintable())[:120] or "Uploaded room"
        finally:
            await photo.close()
        readiness = runtime_status()
        if readiness["setupRequired"]:
            raise StoreError(503, readiness["message"])
        normalized = await run_in_threadpool(normalize_photo, data)
        return await run_in_threadpool(app.state.store.create, normalized, name)

    @app.get("/api/projects/{project_id}")
    def detail(project_id: str):
        return app.state.store.get(project_id)

    @app.post("/api/projects/{project_id}/cancel")
    def cancel(project_id: str):
        return app.state.store.cancel(project_id)

    @app.post("/api/projects/{project_id}/rebuild", status_code=202)
    def rebuild(project_id: str, corrections: dict):
        return app.state.store.rebuild(project_id, validate_corrections(corrections))

    @app.get("/api/projects/{project_id}/assets/{asset}")
    def asset(project_id: str, asset: str, revision: int | None = None):
        path, media, filename = app.state.store.asset(project_id, asset, revision)
        return FileResponse(path, media_type=media, filename=filename, content_disposition_type="attachment" if asset in {"glb", "blend", "scene", "manifest"} else "inline", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    return app


app = create_app()


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--analyze":
        try:
            from backend.reconstruction import analyze_photo, apply_corrections

            def analysis_progress(*args, **kwargs):
                value = next((arg for arg in args if isinstance(arg, (int, float))), kwargs.get("progress", 20))
                if 0 <= value <= 1:
                    value *= 100
                print(json.dumps({"stage": "analyzing", "progress": value}), flush=True)

            source, destination, correction_file = map(Path, sys.argv[2:])
            scene = analyze_photo(source, destination, progress=analysis_progress, cancelled=lambda: False)
            corrections = json.loads(correction_file.read_text())
            if corrections:
                scene = apply_corrections(scene, corrections)
            pending = destination / "scene.json.tmp"
            pending.write_text(json.dumps(scene, indent=2))
            pending.replace(destination / "scene.json")
        except Exception as error:
            print(json.dumps({"stage": "failed", "message": str(error)[:600]}), flush=True)
            sys.exit(1)
    else:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8012")), workers=1)
