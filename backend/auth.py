"""Single-user gatekeeper.

The repo is public, so authorization is enforced server-side on EVERY request:
only ALLOWED_EMAIL may hold a session. Any other Google account that completes
OAuth is rejected with 403 and never gets a session cookie.

AUTH_MODE="dev" bypasses OAuth for local development only. It is honored
ONLY for requests arriving from loopback — if the app is ever exposed while
misconfigured, remote clients still hit the OAuth wall.
"""
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

from .config import settings

router = APIRouter()

oauth = OAuth()
if settings.GOOGLE_CLIENT_ID:
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

# Paths reachable without a session
PUBLIC_PATHS = {"/login", "/auth/google", "/auth/callback", "/manifest.json", "/sw.js"}
PUBLIC_PREFIXES = ("/static/",)

_LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def _is_local(request: Request) -> bool:
    return request.client is not None and request.client.host in _LOOPBACK


class GatekeeperMiddleware(BaseHTTPMiddleware):
    """Reject every request that is not from the single allowed user."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await self._secured(call_next, request)

        # Dev mode: auto-login as the owner — loopback connections only.
        if (
            settings.AUTH_MODE == "dev"
            and not request.session.get("email")
            and _is_local(request)
        ):
            request.session["email"] = settings.ALLOWED_EMAIL

        email = (request.session.get("email") or "").strip().lower()
        if not email:
            if path.startswith("/api/"):
                # Exceptions raised in middleware bypass FastAPI's handlers,
                # so return the response directly.
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            return RedirectResponse("/login")

        # THE gatekeeper check — hard 403 for anyone who is not the owner.
        if not settings.ALLOWED_EMAIL or email != settings.ALLOWED_EMAIL:
            request.session.clear()
            return JSONResponse(
                {"detail": "This is a single-user app. Access denied."}, status_code=403
            )

        return await self._secured(call_next, request)

    @staticmethod
    async def _secured(call_next, request: Request) -> Response:
        """Attach security headers to every response."""
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response


@router.get("/auth/google")
async def auth_google(request: Request):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(500, "Google OAuth is not configured (GOOGLE_CLIENT_ID missing).")
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        raise HTTPException(status_code=403, detail="OAuth failed.")

    email = (token.get("userinfo", {}).get("email") or "").strip().lower()

    # Gatekeeper at the door: wrong email never receives a session.
    if not settings.ALLOWED_EMAIL or email != settings.ALLOWED_EMAIL:
        raise HTTPException(status_code=403, detail="This is a single-user app. Access denied.")

    request.session["email"] = email
    return RedirectResponse("/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")
