"""Draws the app icon and writes finder.png / finder.ico / finder.icns.

The generated files are committed, so this only needs re-running when the
design changes:  python packaging/icons/make_icons.py
(.icns needs macOS's `iconutil`; the .ico and .png are written anywhere.)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

HERE = Path(__file__).resolve().parent
ACCENT = QColor("#2563eb")
ACCENT_DARK = QColor("#1d4ed8")


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 1024  # design on a 1024 grid

    # Rounded-square background (macOS-style inset so it isn't edge-to-edge).
    bg = QRectF(100 * s, 100 * s, 824 * s, 824 * s)
    grad = QLinearGradient(bg.topLeft(), bg.bottomRight())
    grad.setColorAt(0, QColor("#3b82f6"))
    grad.setColorAt(1, ACCENT_DARK)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(bg, 185 * s, 185 * s)

    # Folder.
    # One united path, filled once, so the tab and body don't leave a seam.
    folder = QPainterPath()
    folder.addRoundedRect(QRectF(230 * s, 300 * s, 230 * s, 110 * s), 30 * s, 30 * s)
    body = QPainterPath()
    body.addRoundedRect(QRectF(230 * s, 350 * s, 520 * s, 360 * s), 40 * s, 40 * s)
    p.setBrush(QColor("#eef2ff"))
    p.drawPath(folder.united(body))

    # Magnifier over the folder's corner.
    center = QPointF(640 * s, 600 * s)
    p.setBrush(ACCENT)
    p.setPen(QPen(QColor("white"), 46 * s))
    p.drawEllipse(center, 130 * s, 130 * s)
    handle = QPen(QColor("white"), 70 * s, cap=Qt.PenCapStyle.RoundCap)
    p.setPen(handle)
    # Starts at the lens ring's outer edge (radius 130 + half the ring width).
    p.drawLine(QPointF(752 * s, 712 * s), QPointF(830 * s, 790 * s))
    p.end()
    return img


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - needed for QImage text/IO plugins
    draw(1024).save(str(HERE / "finder.png"))

    # Windows .ico: Qt's ico writer stores one image per file, so save the
    # largest size Windows uses; it scales down cleanly for smaller views.
    if not draw(256).save(str(HERE / "finder.ico"), "ICO"):
        raise SystemExit("Could not write finder.ico (Qt ico image plugin missing?)")

    if shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "finder.iconset"
            iconset.mkdir()
            for base in (16, 32, 128, 256, 512):
                draw(base).save(str(iconset / f"icon_{base}x{base}.png"))
                draw(base * 2).save(str(iconset / f"icon_{base}x{base}@2x.png"))
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "finder.icns")], check=True)
    else:
        print("iconutil not found (not macOS): finder.icns not regenerated.")
    print("Icons written to", HERE)


if __name__ == "__main__":
    main()
