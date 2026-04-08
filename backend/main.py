import sys
import os

# Add this file's directory (backend/) to sys.path so that
# "from app.main import app" resolves to backend/app/main.py
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from app.main import app  # noqa: F401 - re-exported as Vercel ASGI entrypoint
