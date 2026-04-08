import sys
import os

# With @vercel/python + includeFiles:"backend/**",
# /var/task/backend/ contains the app package.
# CWD on Vercel is the project root (/var/task/).
_backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
_backend = os.path.normpath(_backend)
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from app.main import app as _fastapi_app  # noqa: E402

# Vercel rewrites pass the ORIGINAL request path to the function.
# Strip /_/backend prefix so FastAPI routes (/auth/login etc.) match.
_PREFIX = "/_/backend"


async def app(scope, receive, send):
    if scope.get("type") in ("http", "websocket"):
        path = scope.get("path", "/")
        if path.startswith(_PREFIX):
            stripped = path[len(_PREFIX):] or "/"
            scope = {
                **scope,
                "path": stripped,
                "raw_path": stripped.encode(),
            }
    await _fastapi_app(scope, receive, send)
