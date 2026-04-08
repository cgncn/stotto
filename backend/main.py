import sys
import os
import traceback

# Add backend/ to sys.path so "from app.main import app" resolves correctly
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

# Import FastAPI upfront so we can create a fallback app at top level.
# Vercel's static analyser requires "app" to be an unconditional module-level name.
from fastapi import FastAPI as _FastAPI  # noqa: E402
from fastapi.responses import JSONResponse as _JSONResponse  # noqa: E402

# Default fallback app (overwritten below on successful import)
app = _FastAPI()

_import_error: str | None = None
_import_traceback: str | None = None

try:
    from app.main import app  # noqa: F811 – overwrites the fallback on success
except Exception as _exc:
    _import_error = str(_exc)
    _import_traceback = traceback.format_exc()

    # Attach diagnostic routes to the fallback app so the error is visible
    @app.get("/{path:path}")
    @app.post("/{path:path}")
    async def _debug_error(path: str = ""):
        return _JSONResponse(
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
