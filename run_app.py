"""Convenience runner for PyCharm.

Sets up sys.path correctly so "from engine..." imports work regardless of
where you launch the app from, then hands off to streamlit.

Usage:
    python run_app.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    os.chdir(root)
    cmd = [sys.executable, "-m", "streamlit", "run", "app.py"]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
