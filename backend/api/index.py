import sys
import os
import traceback

_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

_import_error = None
_debug = {}

try:
    from app.main import app  # noqa: F401
except Exception:
    _import_error = traceback.format_exc()
    _debug = {
        "error": _import_error,
        "file": __file__,
        "backend_root": _backend_root,
        "sys_path": sys.path[:10],
        "cwd": os.getcwd(),
        "cwd_contents": os.listdir(os.getcwd()),
        "backend_root_contents": os.listdir(_backend_root) if os.path.isdir(_backend_root) else "NOT A DIR",
    }

    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        app = FastAPI()

        @app.get("/{path:path}")
        @app.post("/{path:path}")
        async def _err(path: str = ""):
            return JSONResponse(status_code=500, content=_debug)

    except Exception as e2:
        # fastapi itself is not importable — absolute minimal fallback
        async def app(scope, receive, send):  # type: ignore
            body = str({"fatal": str(e2), "original": _import_error}).encode()
            await send({"type": "http.response.start", "status": 500,
                        "headers": [[b"content-type", b"application/json"]]})
            await send({"type": "http.response.body", "body": body})
