# PyInstaller spec for Finder.
#
# Build (run from the project root, with the venv from requirements-dev.txt active):
#   pyinstaller packaging/finder.spec --noconfirm
#
# Produces, per OS, under dist/:
#   Windows: dist/Finder/Finder.exe        (folder build) or dist/Finder.exe (onefile)
#   macOS:   dist/Finder.app
#   Linux:   dist/Finder/Finder            (wrap with AppImageTool for an .AppImage)
#
# This one spec file is used on all three platforms; PyInstaller reads
# `sys.platform` at build time via the block below to decide bundle type.

import os
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(PROJECT_ROOT, "app", "main.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules("app"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Windows/Linux: a single onefile executable keeps the "one-go" install promise.
# macOS: build as a folder (EXE + COLLECT) so BUNDLE can wrap it into a .app.
onefile = sys.platform != "darwin"

if onefile:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="Finder",
        debug=False,
        strip=False,
        upx=True,
        console=False,
        onefile=True,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="Finder",
        debug=False,
        strip=False,
        upx=True,
        console=False,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        name="Finder",
    )
    app = BUNDLE(
        coll,
        name="Finder.app",
        icon=None,
        bundle_identifier="com.finder.app",
        info_plist={
            "NSHighResolutionCapable": "True",
            "CFBundleShortVersionString": "1.0.0",
        },
    )
