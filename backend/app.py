"""CPU depth inference. Run from the checkout with python -m uvicorn backend.app:app."""

import base64
import hashlib
import io
import logging
import os
import threading
import time
import warnings
from contextlib import asynccontextmanager

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from backend.model import MODEL_NAME, MODEL_PATH, MODEL_SHA256
from backend.limits import MAX_BODY_BYTES, MAX_UPLOAD_BYTES, RequestLimits
from backend.projects import router as projects_router, worker_config

MAX_PIXELS = 24_000_000
OUTPUT_LONG_EDGE = 1600
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
LOGGER = logging.getLogger("titan.depth")


class DepthEngine:
    def __init__(self):
        self.session: ort.InferenceSession | None = None
        self.error: str | None = None
        self.busy = threading.Lock()

    def load(self) -> None:
        if not MODEL_PATH.is_file():
            self.error = "Depth model is missing. Run python -m backend.download_model."
            return
        with MODEL_PATH.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != MODEL_SHA256:
                self.error = "Depth model checksum failed. Run python -m backend.download_model."
                return
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, os.cpu_count() or 1)
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        try:
            self.session = ort.InferenceSession(str(MODEL_PATH), sess_options=options, providers=["CPUExecutionProvider"])
        except Exception:
            LOGGER.exception("The verified depth model could not be loaded")
            self.error = "The depth engine could not start. Check the backend log."

    def infer(self, photo_bytes: bytes) -> dict:
        if self.session is None:
            raise HTTPException(503, self.error or "The depth engine is still starting.")
        if not self.busy.acquire(blocking=False):
            raise HTTPException(429, "Another photo is processing. Please try again shortly.")
        try:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(photo_bytes)) as image:
                        if image.format not in {"JPEG", "PNG", "WEBP"}:
                            raise HTTPException(415, "Upload a JPG, PNG, or WebP image.")
                        if image.width * image.height > MAX_PIXELS:
                            raise HTTPException(413, "Choose an image with fewer than 24 million pixels.")
                        if min(image.size) < 128:
                            raise HTTPException(422, "The image must be at least 128 pixels in each direction.")
                        image.load()
                        corrected = ImageOps.exif_transpose(image).convert("RGB")
            except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
                raise HTTPException(422, "This image could not be read. Try a JPG, PNG, or WebP photo.") from None
            except (Image.DecompressionBombError, Image.DecompressionBombWarning):
                raise HTTPException(413, "Choose an image with fewer than 24 million pixels.") from None

            source_width, source_height = corrected.size
            corrected.thumbnail((OUTPUT_LONG_EDGE, OUTPUT_LONG_EDGE), Image.Resampling.LANCZOS)
            width, height = corrected.size
            # The released model expects 518 x 518 RGB, normalized with ImageNet statistics.
            pixels = np.asarray(corrected.resize((518, 518), Image.Resampling.BICUBIC), dtype=np.float32) / 255.0
            pixels = (pixels - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
            tensor = np.ascontiguousarray(pixels.transpose(2, 0, 1)[None])
            started = time.perf_counter()
            output = self.session.run(None, {self.session.get_inputs()[0].name: tensor})[0]
            inference_ms = round((time.perf_counter() - started) * 1000)
            depth = np.squeeze(output)
            if depth.ndim != 2 or not np.isfinite(depth).all():
                raise HTTPException(500, "The model could not estimate depth for this photo.")
            low, high = float(depth.min()), float(depth.max())
            if high - low < 1e-6:
                raise HTTPException(422, "This image has too little detail to estimate depth. Try another photo.")
            # Relative inverse depth: brighter pixels represent nearer surfaces, never meters.
            normalized = np.rint((depth - low) * (255.0 / (high - low))).clip(0, 255).astype(np.uint8)
            depth_image = Image.fromarray(normalized).resize((width, height), Image.Resampling.BILINEAR)
            encoded = io.BytesIO()
            depth_image.save(encoded, format="PNG")
            return {
                "depth": "data:image/png;base64," + base64.b64encode(encoded.getvalue()).decode("ascii"),
                "width": width,
                "height": height,
                "sourceWidth": source_width,
                "sourceHeight": source_height,
                "model": MODEL_NAME,
                "depthConvention": "near-is-white",
                "inferenceMs": inference_ms,
                "metric": False,
            }
        finally:
            self.busy.release()


engine = DepthEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(engine.load)
    yield


app = FastAPI(title="Titan Space Studio", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(RequestLimits)
app.include_router(projects_router)


@app.get("/api/health")
def health():
    return {"ready": True, "depthReady": engine.session is not None, "model": MODEL_NAME, "error": engine.error, "workerConfigured": bool(worker_config())}


@app.post("/api/depth")
async def estimate_depth(photo: UploadFile):
    try:
        photo_bytes = await photo.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await photo.close()
    if len(photo_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Choose an image smaller than 15 MB.")
    if not photo_bytes:
        raise HTTPException(422, "Choose a photo first.")
    return await run_in_threadpool(engine.infer, photo_bytes)
