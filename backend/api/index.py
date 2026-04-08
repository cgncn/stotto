import sys
import os
import traceback

# Vercel runs with CWD = service root (backend/).
# Insert both CWD and parent of this file into sys.path.
_cwd = os.getcwd()
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for _p in (_cwd, _parent):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_import_error = None
try:
    from app.main import app  # noqa: E402
except Exception:
    _import_error = traceback.format_exc()
    _debug_info = {
        "cwd": _cwd,
        "parent": _parent,
        "file": __file__,
        "sys_path": sys.path[:8],
        "cwd_files": os.listdir(_cwd) if os.path.isdir(_cwd) else [],
        "error": _import_error,
    }

    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI()

    @app.get("/{path:path}")
    @app.post("/{path:path}")
    async def _error_handler(path: str):
        return JSONResponse(status_code=500, content=_debug_info)
