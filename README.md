# Finder — Desktop File Search & Restructuring Tool (Phase 1)

A local, offline desktop tool for CA/finance file archives: very fast file
search over an indexed folder, and safe, confirmation-driven restructuring
and renaming for messy folders. No AI, no file-content reading, no network
access — everything is built on a local SQLite index of file names, paths,
and filesystem metadata.

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for how to use the app, and
[docs/DEVELOPER.md](docs/DEVELOPER.md) for the architecture and how to build
installers.

## Quick start (from source)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

## Try it on the sample data

```bash
python sample_data/generate_sample.py
python -m app.main
# In the app: Index Management -> Select root folder -> sample_data/Sample_Messy_Folder
```

## Run the tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Build a standalone installer

```bash
pip install -r requirements-dev.txt
pyinstaller packaging/finder.spec --noconfirm
```

See [docs/DEVELOPER.md](docs/DEVELOPER.md#packaging) for per-OS notes
(Windows EXE, macOS .app/DMG, Linux AppImage).

## Project layout

```
app/
  core/      Indexing, search, metadata extraction, mismatch detection,
             restructure planning, migration execution — no Qt imports,
             fully unit-testable.
  ui/        PyQt6 screens, background workers, styling.
  main.py    Entry point.
tests/       Unit + integration tests for app/core.
sample_data/ Sample messy folder generator, for demos and testing.
packaging/   PyInstaller spec + per-OS build notes.
docs/        User guide and developer/architecture docs.
```
