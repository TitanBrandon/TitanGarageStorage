"""Upload limits shared by local and hosted app servers."""

from fastapi import HTTPException
from fastapi.responses import JSONResponse

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_BODY_BYTES = MAX_UPLOAD_BYTES + 64 * 1024


class RequestLimits:
    """Cap multipart bodies before parsing and reject cross-site browser uploads."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        if scope["method"] == "POST" and headers.get(b"sec-fetch-site") == b"cross-site":
            return await JSONResponse({"detail": "Cross-site uploads are not allowed."}, status_code=403)(scope, receive, send)
        try:
            declared_size = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid request length."}, status_code=400)(scope, receive, send)
        if declared_size > MAX_BODY_BYTES:
            return await JSONResponse({"detail": "Choose an image smaller than 15 MB."}, status_code=413)(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_BODY_BYTES:
                    raise HTTPException(413, "Choose an image smaller than 15 MB.")
            return message

        return await self.app(scope, limited_receive, send)
