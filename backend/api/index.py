import sys
import os

# When Vercel runs this, CWD is the service root (backend/).
# Ensure it's on sys.path so `app` package is importable.
cwd = os.getcwd()
if cwd not in sys.path:
    sys.path.insert(0, cwd)

# Also add the directory containing this file's parent (belt-and-suspenders)
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if here not in sys.path:
    sys.path.insert(0, here)

from app.main import app  # noqa: E402
