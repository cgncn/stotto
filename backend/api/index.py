import sys
import os

# Add the backend root directory to sys.path so `app` package is importable
backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.main import app  # noqa: E402 — must be after sys.path setup
