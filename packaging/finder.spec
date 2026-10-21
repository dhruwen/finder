# PyInstaller spec for Finder.
#
# Build (run from the project root, with the venv from requirements-dev.txt active):
#   pyinstaller packaging/finder.spec --noconfirm
#
# Produces, per OS, under dist/:
#   Windows: dist/Finder/Finder.exe   (+ its support files; wrapped into a
#                                       one-click installer by packaging/windows/finder.iss)
#   macOS:   dist/Finder.app          (wrapped into a .dmg by packaging/macos/make_dmg.sh)
#   Linux:   dist/Finder/Finder       (wrap with AppImageTool for an .AppImage)
#
# Always a folder ("onedir") build, never "onefile": with spaCy bundled, a
# onefile exe would unpack a few hundred MB to a temp folder on every single
# launch. The installer/DMG gives users the one-click experience instead.

import os
import re
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_all

block_cipher = None
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICONS = os.path.join(PROJECT_ROOT, "packaging", "icons")

with open(os.path.join(PROJECT_ROOT, "app", "__init__.py"), encoding="utf-8") as f:
    VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', f.read()).group(1)

# Bundled so Help > User Guide and the stylesheet's check-mark image work in
# the packaged app too (read at runtime via app/ui/resources.resource_path,
# which resolves to sys._MEIPASS in a frozen build).
datas = [
    (os.path.join(PROJECT_ROOT, "docs", "USER_GUIDE.md"), "docs"),
    (os.path.join(PROJECT_ROOT, "app", "ui", "assets"), os.path.join("app", "ui", "assets")),
]
binaries = []
hiddenimports = collect_submodules("app")

# spaCy + its small multilingual NER model (app/core/ner.py) are optional at
# import time but, when present, need their data files (model weights,
# vocab, meta.json) and C-extension submodules collected explicitly —
# PyInstaller's static analysis can't see spaCy's dynamic imports on its own.
# If these packages aren't installed, collect_all() below just returns
# nothing and the build proceeds without them; the app still runs fine, it
# just falls back to non-AI restructuring (see app/core/ner.is_available()).
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
    excludes=["tkinter", "test", "unittest", "pytest"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if sys.platform == "win32":
    icon = os.path.join(ICONS, "finder.ico")
elif sys.platform == "darwin":
    icon = os.path.join(ICONS, "finder.icns")
else:
    icon = None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Finder",
    debug=False,
    strip=False,
    # UPX-compressed Qt/spaCy DLLs are a classic antivirus false positive
    # on Windows and save little; leave binaries as they are.
    upx=False,
    console=False,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Finder",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Finder.app",
        icon=icon,
        bundle_identifier="com.finder.app",
        version=VERSION,
        info_plist={
            "CFBundleName": "Finder",
            "CFBundleDisplayName": "Finder",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
