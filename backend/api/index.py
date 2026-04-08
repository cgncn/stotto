import sys
import os

# With Vercel `functions` + includeFiles:"backend/**",
# files are deployed at /var/task/backend/**.
# __file__ = /var/task/backend/api/index.py
# dirname(dirname(__file__)) = /var/task/backend  → contains app/
_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from app.main import app  # noqa: F401
