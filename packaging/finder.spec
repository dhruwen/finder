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
from PyInstaller.utils.hooks import collect_submodules, collect_all

block_cipher = None
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# spaCy + its small multilingual NER model (app/core/ner.py) are optional at
# import time but, when present, need their data files (model weights,
# vocab, meta.json) and C-extension submodules collected explicitly —
# PyInstaller's static analysis can't see spaCy's dynamic imports on its own.
# If these packages aren't installed, collect_all() below just returns
# nothing and the build proceeds without them; the app still runs fine, it
# just falls back to non-AI restructuring (see app/core/ner.is_available()).
# Bundled so Help > User Guide works in the packaged app too (read at
# runtime via app/ui/resources.resource_path, which resolves to sys._MEIPASS
# in a frozen build).
datas, binaries, hiddenimports = [
    (os.path.join(PROJECT_ROOT, "docs", "USER_GUIDE.md"), "docs"),
], [], collect_submodules("app")
for pkg in ("spacy", "thinc", "xx_ent_wiki_sm"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

a = Analysis(
    [os.path.join(PROJECT_ROOT, "app", "main.py")],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
