"""Minimal fail-closed authentication for the single-user hosted JobPilot."""
import base64
import binascii
import hmac
import os
from urllib.parse import urlparse

from fastapi.responses import PlainTextResponse


def hosted_mode():
    # Render sets RENDER=true for hosted services. Never allow missing manual
    # configuration to silently expose applicant personal data publicly.
    on_render = os.environ.get("RENDER", "").strip().lower() == "true"
    explicit = os.environ.get("JOBPILOT_HOSTED", "").strip().lower() in ("1", "true", "yes")
    return on_render or explicit


def install_security(app):
    password = os.environ.get("JOBPILOT_ACCESS_PASSWORD", "")
    if hosted_mode() and len(password) < 16:
        raise RuntimeError("Hosted JobPilot requires JOBPILOT_ACCESS_PASSWORD of at least 16 characters")

    @app.middleware("http")
    async def protect_private_data(request, call_next):
        if not hosted_mode() or request.url.path == "/healthz":
            return await call_next(request)

        def unauthorized():
            return PlainTextResponse(
                "JobPilot requires a password", status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="JobPilot", charset="UTF-8"', "Cache-Control": "no-store"}
            )

        try:
            scheme, token = request.headers.get("authorization", "").split(" ", 1)
            if scheme.lower() != "basic":
                return unauthorized()
            decoded = base64.b64decode(token, validate=True).decode("utf-8")
            username, supplied = decoded.split(":", 1)
            if username != "jobpilot" or not hmac.compare_digest(supplied, password):
                return unauthorized()
        except (ValueError, UnicodeError, binascii.Error):
            return unauthorized()

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin") or request.headers.get("referer", "")
            if not origin or urlparse(origin).netloc.lower() != request.headers.get("host", "").lower():
                return PlainTextResponse("Cross-site request blocked", status_code=403)

        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
