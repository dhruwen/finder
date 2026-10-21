# Finder — Desktop File Search & Restructuring Tool (Phase 1)

A local, offline desktop tool for CA/finance and general corporate file
archives: very fast file search over an indexed folder, and safe,
confirmation-driven restructuring and renaming for messy folders. Client and
document-type detection are learned from each folder's own files (not a
hardcoded finance-only list — a law firm's "NDA"/"Deposition" or an
engineering team's own recurring category words get picked up just as well
as a CA's "ITR"/"GST"), so the same tool works on any corporate file
structure. Search and browsing are pure logic/index — no AI, no
file-content reading, no network access. The Restructure wizard optionally
uses a small, fully-local NER model to further improve client/employee name
detection (see [docs/DEVELOPER.md](docs/DEVELOPER.md#local-ai-assist-restructuring-only));
it never phones home and can be turned off in Settings.

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

## Build the one-click installers

GitHub Actions builds both on every relevant PR and on version tags
(`.github/workflows/build-installers.yml`):

- **Windows:** `FinderSetup-<version>.exe`: double-click, no admin rights
  needed, everything (Python, Qt, the local AI model) included.
- **macOS:** `Finder-<version>.dmg`: drag Finder to Applications.

Get them from the workflow run's **Artifacts**, or from the GitHub Release
created when you push a tag like `v1.0.0`. To build locally instead (Python
3.12), see [docs/DEVELOPER.md](docs/DEVELOPER.md#packaging).

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
