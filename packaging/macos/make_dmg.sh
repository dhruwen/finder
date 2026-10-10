#!/usr/bin/env bash
# Wraps dist/Finder.app into a drag-to-install disk image:
#   dist/installer/Finder-<version>.dmg
# Run on macOS after `pyinstaller packaging/finder.spec --noconfirm`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/app/__init__.py")"
APP="$ROOT/dist/Finder.app"
OUT_DIR="$ROOT/dist/installer"
DMG="$OUT_DIR/Finder-$VERSION.dmg"

[ -d "$APP" ] || { echo "Missing $APP — run PyInstaller first." >&2; exit 1; }

# Ad-hoc sign the whole bundle so Apple Silicon Macs will launch it (an
# unsigned arm64 binary is killed outright). This is NOT a Developer ID
# signature: Gatekeeper will still ask the user to confirm on first open.
codesign --force --deep --sign - "$APP"

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

mkdir -p "$OUT_DIR"
rm -f "$DMG"
hdiutil create -volname "Finder $VERSION" -srcfolder "$STAGING" -ov -format UDZO "$DMG" >/dev/null
echo "Created $DMG"
