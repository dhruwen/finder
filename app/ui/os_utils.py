"""Cross-platform "open file" / "reveal in file manager" helpers."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

# File managers to try, in order: (executable, select_flag_or_None).
# nautilus/dolphin take an explicit "--select <file>" flag; nemo/thunar/
# pcmanfm highlight the given file by default when passed its path directly.
# Anything else falls back to just opening the parent folder.
_LINUX_FILE_MANAGERS: list[tuple[str, str | None]] = [
    ("nautilus", "--select"),  # GNOME
    ("dolphin", "--select"),   # KDE
    ("nemo", None),            # Cinnamon
    ("thunar", None),          # XFCE
    ("pcmanfm", None),         # LXDE
]


def open_file(path: str) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def reveal_in_file_manager(path: str) -> bool:
    """Open the file's folder in the OS file manager, highlighting the file
    itself where the platform/desktop environment supports it (Windows
    Explorer, macOS Finder, GNOME Files, KDE Dolphin). Falls back to just
    opening the containing folder everywhere else."""
    p = Path(path)
    try:
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(p)], check=False)
            return True
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(p)], check=False)
            return True

        for cmd, select_flag in _LINUX_FILE_MANAGERS:
            if shutil.which(cmd):
                args = [cmd, select_flag, str(p)] if select_flag else [cmd, str(p)]
                subprocess.run(args, check=False)
                return True

        target = p.parent if p.is_file() else p
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
    except OSError:
        return False
