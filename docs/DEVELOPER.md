# Finder — Developer / Architecture Guide

## Stack

- **Python 3.10+**, no AI/ML dependencies in Phase-1.
- **PyQt6** for the desktop UI.
- **SQLite** (stdlib `sqlite3`) with an **FTS5** virtual table for free-text
  search, one index database per indexed root.
- **PyInstaller** for one-file/one-bundle packaging on Windows/macOS/Linux.

## Layout

```
app/
  core/                     # Pure Python, no Qt imports — unit-testable in isolation.
    config.py               # Settings persistence (roots, index locations, prefs).
    db.py                   # SQLite schema (files + files_fts + index_meta), connect/upsert.
    metadata_extractor.py   # Regex/keyword extraction: client, doc type, year, month.
    indexer.py              # Filesystem walk -> extract -> upsert; incremental refresh.
    mismatch.py             # Folder-metadata vs filename-metadata comparison.
    search.py               # SearchFilters -> SQL (WHERE + FTS5 MATCH).
    restructure.py          # Plans old-path -> new-path moves/renames (pure; no disk I/O).
    migration.py            # Executes an approved plan; writes CSV/JSON report.
    size_estimate.py        # Pre-scan size/row-count estimate before first index.
  ui/
    app_state.py            # Shared AppState (current root, DB connection, settings) + Qt signals.
    workers.py               # QThread wrappers around indexer/restructure/migration.
    main_window.py           # QMainWindow: HomeScreen + a Settings button, nothing else.
    home_screen.py           # The single main page: folder picker, search box, basic
                              # filters (Client/Doc type/Year), a collapsible "More
                              # filters" panel, and the results table.
    settings_dialog.py       # Everything else, behind ⚙ Settings: a left-nav dialog
                              # with Index Management / Restructure & Rename / Warnings /
                              # Preferences pages (wraps index_screen.py, warnings_screen.py,
                              # settings_screen.py, restructure_wizard.py).
    index_screen.py          # Index Management page content.
    restructure_wizard.py    # QWizard: root -> mode -> preview -> confirm -> progress -> done.
    warnings_screen.py       # Mismatch list page content.
    settings_screen.py       # Preferences + About page content.
    os_utils.py               # Cross-platform "open file" / "reveal in folder".
    style.py                  # App-wide QSS stylesheet.
  main.py                    # Entry point (creates QApplication, MainWindow).
```

**UI philosophy:** the main window shows exactly one page (`HomeScreen`) —
pick a folder, search it. Everything that isn't part of that everyday loop
(rebuilding the index, restructuring, mismatch warnings, preferences) lives
in `SettingsDialog`, opened by the single gear button in the top bar. This
keeps the app approachable for non-technical users: there's nothing to
misclick into from the main page.

**Why the core/ui split:** `app/core` has zero Qt imports, so every
indexing, search, extraction, mismatch, and restructure-planning rule is
testable with plain `pytest` and reusable if the UI layer is ever replaced.
`app/ui` is a thin layer that wires `app/core` functions to widgets and
background threads.

## Index schema (`app/core/db.py`)

One SQLite database per indexed root (default location:
`<root>/.finder_index/index.sqlite3`, overridable in Settings).

- `files` — one row per indexed file: `path` (unique), `name`, `parent_dir`,
  `extension`, `size_bytes`, `modified_at`, extracted `client_name` /
  `doc_type` / `year` / `month` (best of filename-derived and
  folder-derived), the raw `folder_*` variants used for mismatch detection,
  and `mismatch_flag` / `mismatch_reason`. Indexed on every filter column
  used by `search.py`.
- `files_fts` — FTS5 external-content table (`content='files'`) over
  `name`, `path`, `client_name`, `doc_type`, `tokens`, kept in sync with
  `files` via `INSERT`/`UPDATE`/`DELETE` triggers.
- `index_meta` — one row per root: last indexed time, file count, total
  bytes. Powers the Index Management stats panel.

## Metadata extraction (`app/core/metadata_extractor.py`)

Rule-based only — regex patterns for years (`FY23-24`, `2024`, `20240315`),
months (word or embedded in a date), and a `DOC_TYPE_KEYWORDS` map (ITR,
Audit, GST, TDS, Salary, Form16, …). Client-name extraction:

1. Build a candidate vocabulary of "known clients" from folder names
   encountered in a first (cheap) pass over the tree
   (`build_known_clients`), filtering out structural words
   (`Received`, `Documents`, doc-type keywords, pure years, …).
2. Match file/folder text against that vocabulary first; fall back to
   picking the longest leftover token after stripping recognized
   doc-type/date/structural tokens.

This is intentionally simple and keyword-driven so **Phase-2 can swap in a
user-editable rule set** without changing call sites — every function here
takes plain strings/lists in and returns plain values out.

## Mismatch detection (`app/core/mismatch.py`)

Compares metadata extracted from the *folder path* against metadata
extracted from the *file name*. Flags a file only when both sides
confidently extracted a value and they disagree (substring matches are not
flagged, to avoid noise from "John" vs "John Sharma").

## Restructuring (`app/core/restructure.py` + `migration.py`)

`plan_restructure()` is pure: it reads already-indexed rows and returns a
`RestructurePlan` (list of old-path/new-path pairs, conflict notes, new
folders needed) without touching disk. `migration.apply_plan()` executes an
approved plan:

- Re-validates every path stays inside the selected root before moving
  anything (defense in depth beyond the UI-level confirmation).
- `dry_run=True` runs the identical code path but skips the actual
  `shutil.move`, so preview and real runs can't drift apart.
- Updates the `files` table's `path`/`name`/`parent_dir` for successfully
  moved files (the FTS triggers keep search in sync automatically).
- Returns a list of `MigrationResult` (old path, new path, status, error),
  written to CSV/JSON by `write_report()`.

## Background work (`app/ui/workers.py`)

Indexing and file operations run on `QThread` subclasses
(`IndexWorker`, `RestructurePlanWorker`, `RestructureApplyWorker`), each
opening its own SQLite connection (SQLite supports concurrent connections
to one file; WAL mode is enabled in `db.connect`). Progress/finished/failed
are `pyqtSignal`s consumed by the UI thread — screens never touch the
filesystem or SQLite directly on the UI thread for anything that could be
slow.

## Extending for Phase-2 / Phase-3

- **Custom rules (Phase-2):** replace the constants in
  `metadata_extractor.py` (`DOC_TYPE_KEYWORDS`, `STRUCTURAL_WORDS`,
  patterns) with values loaded from a user-editable config file; keep the
  function signatures (`extract_year(text)`, `extract_doc_type(text)`, …)
  unchanged so `indexer.py` and `restructure.py` don't need to change.
- **Custom structure/naming templates (Phase-2):** `restructure.py`'s
  `_build_new_path()` is the single place the canonical path/name template
  lives — parameterize it instead of hardcoding
  `Received/<Year>/<Month>/<Client>/<DocType>`.
- **Auto-fix for mismatches (Phase-2):** `mismatch.py` already returns a
  structured reason; add a suggested-path function alongside
  `detect_mismatch()` and a new wizard step that reuses
  `migration.apply_plan()`.
- **AI summaries / NL queries (Phase-3):** would sit entirely above
  `app/core/search.py` — e.g. a new module that turns a natural-language
  query into a `SearchFilters` instance, or a summarization step that reads
  file contents (a capability Phase-1 deliberately does not have). No
  changes needed to the index schema for this.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

- `tests/test_metadata_extractor.py` — year/month/doc-type/client extraction.
- `tests/test_mismatch.py` — mismatch detection rules.
- `tests/test_indexer_search.py` — end-to-end: scan a temp folder, verify
  index contents, run filtered/free-text searches, verify incremental
  removal of deleted files.
- `tests/test_restructure.py` — plan generation (full vs rename-only),
  dry-run vs real `apply_plan`, refusal to write outside the root, CSV
  report generation.

All of `app/core` is Qt-free, so these run without a display server. The UI
layer was additionally smoke-tested end-to-end (index -> search -> warnings
-> restructure plan -> apply -> re-index) driving the real `QThread` worker
classes under `QT_QPA_PLATFORM=offscreen`.

## Packaging

All builds use the single spec file `packaging/finder.spec`, run from the
project root with the dev requirements installed:

```bash
pip install -r requirements-dev.txt
pyinstaller packaging/finder.spec --noconfirm
```

- **Windows:** produces `dist/Finder.exe` (onefile). Distribute that single
  file directly, or wrap it with an installer tool (e.g. Inno Setup) if you
  want a Start Menu entry / uninstaller — optional for Phase-1.
- **macOS:** produces `dist/Finder.app`. Build on macOS (PyInstaller does
  not cross-compile). Wrap in a DMG for distribution:
  ```bash
  hdiutil create -volname Finder -srcfolder dist/Finder.app -ov -format UDZO Finder.dmg
  ```
  The app is unsigned in Phase-1; users need the Gatekeeper workaround
  documented in the User Guide (Control-click -> Open) unless you later add
  an Apple Developer ID and codesign/notarize the build.
- **Linux:** produces `dist/Finder` (onefile ELF binary). Wrap it as an
  AppImage with [`appimagetool`](https://github.com/AppImage/AppImageKit):
  ```bash
  mkdir -p Finder.AppDir/usr/bin
  cp dist/Finder Finder.AppDir/usr/bin/
  # add Finder.AppDir/Finder.desktop and Finder.AppDir/AppRun (see AppImage docs)
  appimagetool Finder.AppDir Finder-x86_64.AppImage
  ```
  A plain tarball of `dist/Finder` plus a one-line run script is an
  acceptable equivalent for Phase-1 if you'd rather skip AppImage tooling.

Each OS's build must run on that OS (or an equivalent CI runner) —
PyInstaller packages the interpreter and native Qt libraries for the host
platform it runs on; it does not cross-build.

### Known packaging caveat (Linux)

The Qt "xcb" platform plugin PyInstaller bundles depends on the system
having `libxcb-cursor0` (Debian/Ubuntu package name) installed; most desktop
distros already have it via other GTK/Qt apps. If a target machine is
missing it, `apt install libxcb-cursor0` (or the equivalent for that distro)
resolves it. This is a system library, not something PyInstaller can bundle
portably.
