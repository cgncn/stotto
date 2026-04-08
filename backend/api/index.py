import sys
import os

# Add backend root to sys.path so "from app.main import app" works.
# With @vercel/python + includeFiles, __file__ is /var/task/backend/api/index.py
# so dirname(dirname(...)) = /var/task/backend  → finds app/ package.
_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_cwd = os.getcwd()

for _p in (_backend_root, _cwd):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.main import app  # noqa: E402
