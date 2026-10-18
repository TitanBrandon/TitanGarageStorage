"""Password-protected website/API server. Run using python -m backend.hosted."""

import base64
import binascii
from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from backend.limits import RequestLimits
from backend.projects import router as projects_router

ROOT = Path(__file__).resolve().parents[1]


def site_password() -> bytes:
    value = os.environ.get("SITE_PASSWORD", "")
    if len(value) < 16:
        raise RuntimeError("Set SITE_PASSWORD to at least 16 characters before starting the hosted app.")
    return value.encode("utf-8")


class PrivateSite:
    """Use the browser's login prompt for this private prototype and all its APIs."""

    def __init__(self, app):
        self.app = app
        self.password = site_password()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/healthz":
            return await self.app(scope, receive, send)
        header = dict(scope.get("headers", [])).get(b"authorization", b"")
        username, password = b"", b""
        try:
            scheme, token = header.split(b" ", 1)
            if scheme.lower() == b"basic":
                username, password = base64.b64decode(token, validate=True).split(b":", 1)
        except (ValueError, binascii.Error):
            pass
        valid_user = hmac.compare_digest(username, b"titan")
        valid_password = hmac.compare_digest(password, self.password)
        if not (valid_user and valid_password):
            response = PlainTextResponse(
                "Sign in to Space Studio using username titan and your site password.",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Titan Space Studio", charset="UTF-8"', "Cache-Control": "no-store"},
            )
            return await response(scope, receive, send)

        async def private_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"cache-control", b"no-store" if scope["path"].startswith("/api/") else b"private"),
                    (b"vary", b"Authorization"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                ])
                message = {**message, "headers": headers}
            await send(message)

        return await self.app(scope, receive, private_send)


def create_app(static_directory: Path | None = None) -> FastAPI:
    assets = static_directory or ROOT / "dist"

    @asynccontextmanager
    async def lifespan(app):
        site_password()
        if not (assets / "index.html").is_file():
            raise RuntimeError("The website build is missing. Run npm ci and npm run build first.")
        yield

    app = FastAPI(title="Titan Space Studio", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestLimits)
    # Authentication is the outer middleware, before multipart parsing or routing.
    app.add_middleware(PrivateSite)
    app.include_router(projects_router)

    @app.get("/healthz")
    def health():
        return {"ready": True}

    @app.get("/api/{unknown:path}")
    def missing_api(unknown: str):
        return JSONResponse({"detail": "API route not found."}, status_code=404)

    app.mount("/", StaticFiles(directory=assets, html=True, check_dir=False), name="studio")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), workers=1)
