"""Locates bundled resources (e.g. docs/USER_GUIDE.md) whether running from
source or from a PyInstaller-frozen executable, where files listed in the
spec's `datas` are extracted to `sys._MEIPASS` at startup."""
from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent.parent  # project root
    return base.joinpath(*parts)
