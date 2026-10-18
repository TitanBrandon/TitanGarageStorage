"""Authenticated same-origin proxy to the separately hosted durable worker."""

import os
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from backend.limits import MAX_BODY_BYTES
from backend.project_store import StoreError, valid_id

router = APIRouter(prefix="/api/projects")
TIMEOUT = httpx.Timeout(connect=10, read=90, write=60, pool=10)


def worker_config():
    url, token = os.environ.get("WORKER_URL", "").strip().rstrip("/"), os.environ.get("WORKER_TOKEN", "").strip()
    if not url or not token:
        return None
    try:
        parsed = urlsplit(url)
        parsed.port  # Reject malformed or out-of-range configured ports.
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/") or not parsed.hostname:
            return None
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and (local or os.environ.get("WORKER_ALLOW_HTTP") == "1")):
            return None
    except ValueError:
        return None
    return url, token


def require_worker():
    configured = worker_config()
    if not configured:
        raise HTTPException(503, "Reconstruction worker setup is required. Configure WORKER_URL and WORKER_TOKEN for a worker with a persistent PROJECTS_DIR volume.")
    return configured


def checked_id(project_id):
    try:
        return valid_id(project_id)
    except StoreError as error:
        raise HTTPException(error.status, error.message) from None


def make_client():
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False)


async def proxy(request, suffix="", *, asset=False, status_check=False):
    base, token = require_worker()
    client = make_client()
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if request.headers.get("content-type"):
        headers["Content-Type"] = request.headers["content-type"]
    if asset and request.headers.get("range"):
        headers["Range"] = request.headers["range"]
    query = {}
    if "revision" in request.query_params:
        try:
            revision = int(request.query_params["revision"])
            if not 1 <= revision <= 1_000_000:
                raise ValueError
        except ValueError:
            await client.aclose()
            raise HTTPException(422, "Invalid project revision.") from None
        query["revision"] = revision
    received = 0

    async def content():
        nonlocal received
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_BODY_BYTES:
                raise HTTPException(413, "Choose an image smaller than 15 MB.")
            yield chunk

    try:
        outgoing = client.build_request(request.method, base + "/api/projects" + suffix, headers=headers, params=query, content=content() if request.method == "POST" else None)
        response = await client.send(outgoing, stream=True)
    except (httpx.RequestError, httpx.TimeoutException):
        await client.aclose()
        raise HTTPException(503, "The reconstruction worker cannot be reached. Check its address, network access, and persistent worker service.") from None
    except BaseException:
        await client.aclose()
        raise
    if response.status_code in (401, 403):
        await response.aclose()
        await client.aclose()
        raise HTTPException(503, "The reconstruction worker rejected authentication. Set matching WORKER_TOKEN secrets on the web app and worker.")
    if response.status_code >= 500:
        await response.aclose()
        await client.aclose()
        raise HTTPException(503, "The reconstruction worker could not process this request. Check its service and storage status.")
    if not asset or response.status_code >= 400:
        try:
            body = await response.aread()
            if len(body) > 8 * 1024 * 1024:
                raise HTTPException(502, "Worker response exceeded its supported size.")
            try:
                payload = response.json()
            except ValueError:
                raise HTTPException(502, "The worker returned an unreadable response.") from None
            # Tokens are only transmitted in a request header, never reflected to browsers.
            if token in body.decode("utf-8", errors="replace"):
                raise HTTPException(502, "The worker returned an unsafe response.")
            return JSONResponse(payload, response.status_code, headers={"Cache-Control": "no-store"})
        finally:
            await response.aclose()
            await client.aclose()

    async def close():
        await response.aclose()
        await client.aclose()

    forwarded = {name: response.headers[name] for name in ("content-length", "content-range", "accept-ranges", "content-disposition") if name in response.headers}
    forwarded["Cache-Control"] = "no-store"
    forwarded["X-Content-Type-Options"] = "nosniff"
    return StreamingResponse(response.aiter_bytes(), status_code=response.status_code, media_type=response.headers.get("content-type", "application/octet-stream"), headers=forwarded, background=BackgroundTask(close))


@router.get("/status")
async def status(request: Request):
    if not worker_config():
        return {"configured": False, "workerReachable": False, "setupRequired": True, "message": "Connect a Blender reconstruction worker with durable storage. WORKER_URL and WORKER_TOKEN are required on this web app."}
    try:
        result = await proxy(request, "/status", status_check=True)
        if result.status_code != 200:
            return {"configured": True, "workerReachable": False, "setupRequired": True, "message": "The worker status could not be verified."}
        return result
    except HTTPException as error:
        return {"configured": True, "workerReachable": False, "setupRequired": True, "message": error.detail}


@router.get("")
async def projects(request: Request):
    return await proxy(request)


@router.post("", status_code=202)
async def create(request: Request):
    return await proxy(request)


@router.get("/{project_id}")
async def detail(project_id: str, request: Request):
    return await proxy(request, "/" + checked_id(project_id))


@router.post("/{project_id}/cancel")
async def cancel(project_id: str, request: Request):
    return await proxy(request, "/" + checked_id(project_id) + "/cancel")


@router.post("/{project_id}/rebuild", status_code=202)
async def rebuild(project_id: str, request: Request):
    return await proxy(request, "/" + checked_id(project_id) + "/rebuild")


@router.get("/{project_id}/assets/{asset}")
async def asset(project_id: str, asset: str, request: Request):
    if asset not in {"source", "preview", "glb", "blend", "scene", "manifest"}:
        raise HTTPException(404, "Unknown project asset.")
    return await proxy(request, "/" + checked_id(project_id) + "/assets/" + asset, asset=True)
