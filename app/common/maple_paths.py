"""Shared ``sys.path`` bootstrap for Streamlit entrypoints under ``app/``."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_app_import_paths() -> None:
    """Register project root and ``src`` so ``app.*`` and ``src.*`` imports work."""
    project_root = Path(__file__).resolve().parents[2]
    src_root = project_root / "src"
    for path in (project_root, src_root):
        p = str(path)
        if p not in sys.path:
            sys.path.insert(0, p)
