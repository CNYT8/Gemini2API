import logging

from fastapi import Request, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)


STATIC_EXTENSIONS = {".html", ".css", ".js", ".ico", ".png", ".jpg", ".svg", ".woff", ".woff2", ".ttf"}


async def verify_api_key(request: Request):
    path = request.url.path

    if path == "/health":
        return

    if path in ("/", "/login.html", "/index.html"):
        return

    from pathlib import PurePosixPath
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in STATIC_EXTENSIONS:
        return

    if path.startswith("/app/") or path.startswith("/components/"):
        return

    key = None

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        key = auth_header[7:].strip()

    if not key:
        key = request.headers.get("x-api-key", "").strip()

    if not key:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "Missing API key. Use Authorization: Bearer sk-xxx or x-api-key header.", "type": "auth_error"}},
        )

    if key != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "Invalid API key.", "type": "auth_error"}},
        )
