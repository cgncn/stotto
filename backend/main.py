import sys
import os
import traceback

# Add backend/ to sys.path so "from app.main import app" resolves correctly
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

_import_error = None
_import_traceback = None

try:
    from app.main import app  # noqa: F401 - re-exported as Vercel ASGI entrypoint
except Exception as _e:
    _import_error = str(_e)
    _import_traceback = traceback.format_exc()

if _import_error:
    # Fallback: expose the exact import error so we can debug
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI()

    @app.get("/{path:path}")
    @app.post("/{path:path}")
    async def _debug_error(path: str = ""):
        return JSONResponse(
            status_code=500,
            content={
                "error": _import_error,
                "traceback": _import_traceback,
                "sys_path": sys.path,
                "python_version": sys.version,
                "cwd": os.getcwd(),
                "file": __file__,
            },
        )
