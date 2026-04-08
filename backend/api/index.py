import sys
import os

# Vercel runs with CWD = service root (backend/).
# Insert both CWD and parent of this file into sys.path.
_cwd = os.getcwd()
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for _p in (_cwd, _parent):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.main import app  # noqa: E402
