import sys
import os

# Add backend/ to sys.path so "from app.main import app" resolves correctly
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from app.main import app  # noqa: F401 - re-exported as Vercel ASGI entrypoint
