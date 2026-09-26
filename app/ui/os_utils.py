"""Cross-platform "open file" / "reveal in file manager" helpers."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


def open_file(path: str) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def reveal_in_file_manager(path: str) -> bool:
    p = Path(path)
    try:
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(p)], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(p)], check=False)
        else:
            target = p.parent if p.is_file() else p
            return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        return True
    except OSError:
        return False
