"""Server-side World Labs image-to-world integration.

Provider requests follow the official World Labs API examples and Python SDK.
The API key stays on this server. Generation submissions are never retried.
"""

import base64
import io
import os
import re
import threading
import time
import warnings
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Form, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

API_BASE = "https://api.worldlabs.ai/marble/v1"
PROVIDER = "World Labs"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 24_000_000
MAX_LONG_EDGE = 2048
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
router = APIRouter(prefix="/api/worlds")


def configured_key() -> str | None:
    for name in ("WORLDLABS_API_KEY", "WLT_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def provider_status() -> dict:
    return {"configured": bool(configured_key()), "provider": PROVIDER}


def require_key() -> str:
    key = configured_key()
    if not key:
        raise HTTPException(503, "Add WORLDLABS_API_KEY in the environment's secret settings and restart the development server to enable World Labs generation.")
    return key


def validate_id(value: object) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise HTTPException(422, "Invalid world or operation ID.")
    return value


def prepare_photo(photo_bytes: bytes) -> str:
    """Validate bytes, apply orientation, strip metadata and return bounded JPEG."""
    if not photo_bytes:
        raise HTTPException(422, "Choose a photo first.")
    if len(photo_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Choose an image smaller than 15 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(photo_bytes)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"}:
                    raise HTTPException(415, "Upload a JPG, PNG, or WebP image.")
                if original.width * original.height > MAX_PIXELS:
                    raise HTTPException(413, "Choose an image with fewer than 24 million pixels.")
                if min(original.size) < 128:
                    raise HTTPException(422, "The image must be at least 128 pixels in each direction.")
                original.load()
                corrected = ImageOps.exif_transpose(original)
                if corrected.mode in {"RGBA", "LA"} or "transparency" in corrected.info:
                    rgba = corrected.convert("RGBA")
                    image = Image.new("RGB", rgba.size, "white")
                    image.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    image = corrected.convert("RGB")
                image.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=92)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(413, "Choose an image with fewer than 24 million pixels.") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise HTTPException(422, "This image could not be read. Try a JPG, PNG, or WebP photo.") from None
    return base64.b64encode(output.getvalue()).decode("ascii")


def safe_asset_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 8192:
        return None
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        # Official World Labs assets and hosted viewer use these HTTPS domains.
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return None
        if hostname != "worldlabs.ai" and not hostname.endswith(".worldlabs.ai"):
            return None
        key = configured_key()
        if key and key in value:
            return None
    except ValueError:
        return None
    return value


def as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def normalize_world(payload: dict, fallback_id: str) -> dict:
    world = as_dict(payload.get("world")) if "world" in payload else payload
    world_id = world.get("world_id") or world.get("id") or fallback_id
    if not isinstance(world_id, str) or not ID_PATTERN.fullmatch(world_id):
        raise HTTPException(502, "World Labs returned an invalid world ID.")
    splats = as_dict(as_dict(as_dict(world.get("assets")).get("splats")).get("spz_urls"))
    splat_url = next((url for size in ("500k", "100k", "full_res") if (url := safe_asset_url(splats.get(size)))), None)
    world_url = safe_asset_url(world.get("world_marble_url"))
    result = {"state": "ready" if splat_url or world_url else "pending", "worldId": world_id}
    if splat_url:
        result["splatUrl"] = splat_url
    if world_url:
        result["worldUrl"] = world_url
    if not splat_url and not world_url and any(isinstance(value, str) and value for value in splats.values()):
        result["state"] = "failed"
        result["message"] = "This app could not validate the world's asset host. View this world in your World Labs dashboard."
    elif result["state"] == "pending":
        result["message"] = "The world is generated; World Labs is preparing its viewing assets."
    return result


class WorldService:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport
        self.submitting = threading.Lock()
        self.active_operation: str | None = None
        self.active_since: float | None = None

    async def request(self, method: str, path: str, body: dict | None = None) -> dict:
        key = require_key()
        try:
            # Explicitly no redirect following and no transport retries: a POST may be billed.
            async with httpx.AsyncClient(transport=self.transport, timeout=TIMEOUT, follow_redirects=False) as client:
                response = await client.request(method, API_BASE + path, headers={"WLT-Api-Key": key, "Accept": "application/json"}, json=body)
        except httpx.TimeoutException:
            message = "World Labs did not respond in time. Try checking the world again."
            if method == "POST":
                message = "Submission timed out. World Labs may have accepted it; check your World Labs dashboard before starting another paid generation."
            raise HTTPException(504, message) from None
        except httpx.RequestError:
            raise HTTPException(502, "World Labs could not be reached. Check network access to api.worldlabs.ai.") from None
        status = response.status_code
        if status in (401, 403):
            raise HTTPException(503, "World Labs rejected the API key or account access. Check WORLDLABS_API_KEY and your World Labs API access, then restart the server.")
        if status == 402:
            raise HTTPException(402, "World Labs requires available credits. Add credits in your World Labs account before generating a world.")
        if status == 429:
            raise HTTPException(429, "World Labs is limiting requests. Wait before trying again; the app has not retried this request.")
        if status == 404:
            raise HTTPException(404, "World Labs could not find that world or generation operation.")
        if status in (400, 422):
            raise HTTPException(422, "World Labs could not accept this request. Try another photo or check the selected generation model.")
        if not 200 <= status < 300:
            raise HTTPException(502, "World Labs could not complete this request. Check its service status before trying again.")
        try:
            payload = response.json()
        except ValueError:
            raise HTTPException(502, "World Labs returned an unreadable response.") from None
        if not isinstance(payload, dict):
            raise HTTPException(502, "World Labs returned an unexpected response.")
        return payload

    async def generate(self, photo_bytes: bytes, quality: str) -> dict:
        require_key()
        if not self.submitting.acquire(blocking=False):
            raise HTTPException(429, "A World Labs submission is already in progress.")
        try:
            if self.active_operation:
                raise HTTPException(429, "A world is already generating. Resume its progress before starting another paid generation.")
            encoded = await run_in_threadpool(prepare_photo, photo_bytes)
            payload = await self.request("POST", "/worlds:generate", {
                "world_prompt": {
                    "type": "image",
                    "disable_recaption": False,
                    "image_prompt": {"source": "data_base64", "data_base64": encoded, "extension": "jpg"},
                },
                "model": "Marble 0.1-mini" if quality == "mini" else "Marble 0.1-plus",
            })
            operation_id = payload.get("operation_id")
            if not isinstance(operation_id, str) or not ID_PATTERN.fullmatch(operation_id):
                raise HTTPException(502, "World Labs accepted the request but returned no valid operation ID. Check your World Labs dashboard before starting another paid generation.")
            self.active_operation = operation_id
            self.active_since = time.monotonic()
            return {"operationId": operation_id}
        finally:
            self.submitting.release()

    def finish(self, operation_id: str) -> None:
        if self.active_operation == operation_id:
            self.active_operation = None
            self.active_since = None

    async def operation(self, operation_id: str) -> dict:
        validate_id(operation_id)
        payload = await self.request("GET", "/operations/" + operation_id)
        if payload.get("error"):
            self.finish(operation_id)
            # Provider errors may echo user input or credentials; expose a fixed diagnostic.
            return {"state": "failed", "message": "World Labs could not generate this world. Check the operation in your World Labs dashboard before trying another photo."}
        if payload.get("done") is False:
            return {"state": "pending"}
        if payload.get("done") is not True:
            raise HTTPException(502, "World Labs returned an unexpected operation status.")
        response = as_dict(payload.get("response"))
        response = as_dict(response.get("world")) if "world" in response else response
        world_id = response.get("world_id") or response.get("id")
        if not isinstance(world_id, str) or not ID_PATTERN.fullmatch(world_id):
            self.finish(operation_id)
            return {"state": "failed", "message": "World Labs finished without a usable world. Check your World Labs dashboard for this operation."}
        result = await self.world(world_id)
        if result["state"] in {"ready", "failed"}:
            self.finish(operation_id)
        return result

    async def world(self, world_id: str) -> dict:
        validate_id(world_id)
        return normalize_world(await self.request("GET", "/worlds/" + world_id), world_id)


service = WorldService()


@router.get("/status")
def status():
    result = provider_status()
    if service.active_operation:
        result["activeOperationId"] = service.active_operation
    return result


@router.post("", status_code=202)
async def generate_world(photo: UploadFile, quality: Literal["mini", "plus"] = Form("plus")):
    try:
        require_key()
        photo_bytes = await photo.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await photo.close()
    return await service.generate(photo_bytes, quality)


@router.get("/operations/{operation_id}")
async def operation_status(operation_id: str):
    return await service.operation(operation_id)


@router.get("/{world_id}")
async def get_world(world_id: str):
    return await service.world(world_id)
