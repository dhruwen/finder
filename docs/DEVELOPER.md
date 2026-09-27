# Finder — Developer / Architecture Guide

## Stack

- **Python 3.10+**. Search, indexing, and mismatch detection are pure
  logic/regex — no AI/ML anywhere in that path.
- **PyQt6** for the desktop UI.
- **SQLite** (stdlib `sqlite3`) with an **FTS5** virtual table for free-text
  search, one index database per indexed root.
- **spaCy + a small multilingual NER model** (`xx_ent_wiki_sm`, ~40MB),
  used *only* inside the Restructure wizard's preview step to improve
  client/employee name detection. Fully local, optional, and toggleable —
  see [Local AI assist](#local-ai-assist-restructuring-only) below.
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
                             # Optionally consults ner.py to refine client names, and
                             # project_detection.py to skip software-project files.
    ner.py                  # Optional local NER (see "Local AI assist" below). Every
                             # function degrades to returning None if the model isn't
                             # installed — never a hard dependency of anything else.
    project_detection.py    # Detects .git/package.json/requirements.txt/node_modules/...
                             # so restructuring never touches a software project's files.
    migration.py            # Executes an approved plan; writes CSV/JSON report.
    size_estimate.py        # Pre-scan size/row-count estimate before first index.
  ui/
    app_state.py            # Shared AppState (current root, DB connection, settings) + Qt signals.
    workers.py               # QThread wrappers around indexer/restructure/migration.
    main_window.py           # QMainWindow: HomeScreen + the native File/Edit/View/Help
                              # menu bar (QMainWindow.menuBar() — Qt places it
                              # per-platform automatically: in-window on Windows/Linux,
                              # OS-level menu bar on macOS). The menu deliberately does
                              # NOT repeat any action that already has a single, always-
                              # visible on-page button (Choose Folder, Restructure &
                              # Rename, Settings) — those stay page-only, one way to do
                              # each thing. It only adds what has no on-page equivalent
                              # (Open Recent, Copy File Path, Refresh Search, ...) or is
                              # pure OS/window chrome (Quit, About), and those two carry
                              # setMenuRole() so Qt relocates them into the native macOS
                              # app menu. File > Open Recent lists Settings.roots;
                              # switching to an already-indexed recent folder is instant
                              # (no reindex) since AppState just reopens its existing DB
                              # connection.
    home_screen.py           # The single main page: folder picker, search box, basic
                              # filters (Name/Keyword/Year), a collapsible "More
                              # filters" panel, the results table, and a Restructure &
                              # Rename button (disabled until a folder is indexed) that
                              # opens restructure_wizard.RestructureWizard directly.
                              # Double-clicking a result prompts Open File / Open File
                              # Location with a "remember this" checkbox tied to
                              # Settings.default_file_action.
    settings_dialog.py       # Everything that ISN'T a primary on-page action, behind ⚙
                              # Settings: a left-nav dialog with Index Management /
                              # Warnings / Preferences pages (wraps index_screen.py,
                              # warnings_screen.py, settings_screen.py). Restructure &
                              # Rename intentionally does NOT have a page in here — it's
                              # a primary feature with its own on-page button, not a
                              # settings tweak; putting it in both places was the exact
                              # kind of duplication this dialog exists to avoid.
    index_screen.py          # Index Management page content.
    restructure_wizard.py    # QWizard: root -> mode -> preview -> confirm -> progress ->
                              # done. Opened from home_screen.py's on-page button. The
                              # preview step shows a QTabWidget: a QTreeWidget rendering
                              # of the resulting folder layout (folder icon + bold, blue
                              # for folders that don't exist yet, file-type icons via
                              # icons.py, ✨ on AI-improved names, a file count per
                              # folder), and the file-by-file old-path/new-path table
                              # with a per-row AI-assisted marker.
    icons.py                 # Emoji icon lookup by file category (Documents 📄, Code
                              # 💻, ...), shared by the tree view and the home page's
                              # File Type dropdown buttons — no icon assets to bundle.
    warnings_screen.py       # Mismatch list page content.
    settings_screen.py       # Preferences + About page content.
    os_utils.py               # Cross-platform "open file" / "reveal in folder" (the
                               # latter highlights the specific file via Explorer's
                               # /select, Finder's -R, or nautilus/dolphin --select).
    resources.py               # Locates bundled files (e.g. docs/USER_GUIDE.md) whether
                               # running from source or a frozen PyInstaller executable.
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
Audit, GST, TDS, Salary, Form16, …). That fixed map is CA/finance-specific
by design — it's a curated set of unambiguous abbreviations, and stays
useful for exactly that vocabulary. Everything below it is what makes doc
type and client detection work for **any** corporate structure, not just
finance:

**Client names** (`extract_client`):
1. `build_known_clients` makes one cheap pass over the tree's *folder
   names* and treats any name that isn't a structural word (`Received`,
   `Documents`, …), a doc-type keyword, or a pure year/date as a candidate
   client. This alone is already domain-agnostic — it's learning from
   whatever folder names this specific user actually has, not a hardcoded
   list of finance clients.
2. Match file/folder text against that vocabulary first (so a multi-word
   name like "Ramesh Kumar" or "Acme Industries" is captured whole); fall
   back to the longest leftover token after stripping recognized tokens.

**Document types** (`extract_doc_type`) — this is the part that was
finance-only until it wasn't:
1. Check the fixed `DOC_TYPE_KEYWORDS` map first (fast, unambiguous, for the
   common CA/finance abbreviations it covers).
2. If nothing matches, check `discovered_vocab` — see
   `build_doc_type_vocabulary` below. This is what makes a legal firm's
   "NDA"/"Deposition"/"Filing" or an engineering team's own recurring
   category words get classified correctly, with zero hardcoded knowledge
   of those industries.

**`build_doc_type_vocabulary(entries, known_clients)`** learns candidate
document-type words *from this specific tree's own files* — the same "learn
from the data, don't hardcode an industry" idea as `build_known_clients`,
applied to categories instead of names. A token qualifies as a category word
(not a one-off description word) if it:
- appears in at least `min_doc_frequency` different files (default 2), and
- appears across at least `min_spread` different parent folders (default
  2) — i.e. it repeats as a stable label across different
  clients/people/projects, not just as part of one person's own filename
  habit.

If the tree is one flat folder with no subfolders to spread across, the
spread requirement relaxes to frequency alone, since there's nothing to
discriminate against. Client-name tokens are excluded from candidacy so a
client's own name is never mistaken for a document category.

`indexer.scan_root` calls this once per scan (from the same cheap
folder-only pre-pass that already builds `known_clients` — see
`_collect_tree_info`), then passes the result into every `extract_all` call
for that scan. It costs effectively nothing extra: no additional disk walk,
no stat calls, pure in-memory token counting.

**Proof, not assumption:** `tests/test_indexer_search.py::test_indexer_discovers_doc_types_for_non_finance_domain`
indexes a synthetic legal-firm tree (Acme Industries / Beta Holdings / Gamma
LLC, files like "NDA", "Deposition" — none of which exist anywhere in
`DOC_TYPE_KEYWORDS`) and asserts both the full multi-word client names and
the auto-discovered doc types come out correct. It's not a documentation
claim; it's a passing test.

Every function here takes plain strings/lists in and returns plain values
out, so Phase-2's user-editable rule set can layer on top (e.g. a per-root
override list) without changing any call site.

**Extensions** (`normalize_extension`, `extension_category`): a raw filename
suffix only counts as a real extension if it's a known type or passes a
structural sanity check — version/status fragments like `.v2`/`.final` and
bare digits like `.23` are rejected outright (see `_resolve_dd_mm`-adjacent
history: an earlier version over-corrected into a CA-only allowlist that
silently hid real extensions like `.dwg`/`.psd`/`.py` for non-finance users;
it's now backed by Python's stdlib `mimetypes` database instead, so it's
broad by default). `extension_category()` then buckets a recognized
extension into one of a fixed set of domain-agnostic groups (Documents,
Spreadsheets, Presentations, Images, Design, Code, Archives, Email,
Audio/Video, Other) — explicit overrides for the common/ambiguous cases,
falling back to the MIME type's top-level category (`image/`, `audio/`, …)
for anything else. `home_screen.py`'s File Type filter renders this as one
`QToolButton` + popup `QMenu` per category (`_populate_category_filters`) —
only categories actually present in the index get a button at all, and each
button's label shows a live count of how many of its extensions are
checked (e.g. "Code (2) ▾"), so the filter bar stays compact regardless of
how many file types exist in a given folder.

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

**Software-project protection** (`app/core/project_detection.py`):
`plan_restructure()` never restructures files sitting inside a detected
software project (`.git`, `package.json`, `requirements.txt`, `node_modules`,
`.venv`, `Cargo.toml`, and similar markers — see `PROJECT_MARKER_NAMES`).
This matters specifically because the app now works on "any corporate
structure," not just document archives — without this guard, pointing
Restructure at a folder that happens to contain a codebase would scramble
its source layout and break it (broken imports, a git repo with all its
tracked paths rewritten).

`build_project_exclusion_set(all_dirs, root)` computes, for every directory
that appears among the indexed files, whether it IS a project directory or
lives inside one — memoized bottom-up (a directory's own marker check runs
once, then every descendant just inherits the memoized ancestor result) so
this stays cheap even on deep trees. `plan_restructure` skips any row whose
`parent_dir` is in that set (counted in `RestructurePlan.skipped_project_files`)
and separately flags `RestructurePlan.root_is_project` when the *selected
root itself* is a project — in that case `PreviewPage` shows a full-block
explanation and refuses to let the wizard proceed, rather than silently
producing an empty, confusing plan. Verified with a synthetic mixed root
(real documents + an actual `.git`/`package.json`/`node_modules` tree) in
`tests/test_restructure.py` and `tests/test_project_detection.py`.

## Local AI assist (restructuring only)

`plan_restructure(..., use_ai=True)` optionally asks `app/core/ner.py` to
suggest a better client/employee name for each file than the plain
regex/keyword heuristic in `metadata_extractor.py` can find on its own, and
uses it (`_build_new_path`'s `client_override`) when it differs from the
regex-only guess.

**Why this exists:** the regex-only fallback (`extract_client`'s "longest
leftover token" heuristic) only ever picks a single token, so a file named
`Ramesh Kumar Audit FY23-24.pdf` gets grouped under `Ramesh` — the surname is
silently dropped. A real local NER pass catches the full name.

**Model choice, and why not the obvious one:** `en_core_web_sm` (spaCy's
standard English NER model) was tried first and reliably *missed* common
Indian personal names ("Ramesh Kumar", "Suresh Sharma") even given full
sentence context — its training data skews Western. `xx_ent_wiki_sm` (spaCy's
small multilingual model, trained on WikiNER, ~40MB) recognizes these
substantially more often, at the cost of looser entity-span boundaries (it
sometimes swallows a neighboring doc-type/date word). `ner._clean_entity_text`
fixes that by re-running the entity span through the same
`strip_known_tokens()` used elsewhere in `metadata_extractor.py`, trimming it
back to just the name. This was validated empirically, not assumed — see
`tests/test_ner.py` for the specific before/after cases.

**Where it runs, and why not everywhere:** only inside
`RestructurePlanWorker`, which already runs on a background `QThread` behind
a "Analyzing folder…" spinner in the wizard's preview step. It is
deliberately **not** used during normal indexing or search — those must stay
instant, and adding a ~5-20ms-per-file NER pass to every index rebuild would
be a regression, not an improvement. The model itself loads lazily
(`functools.lru_cache`) on first real use (~1-1.5s once, cached after) rather
than at app startup or in `ner.is_available()` (a cheap `importlib.util.find_spec`
check used for the Settings status line, which must not stall the UI).

**Graceful degradation, always:** `ner.is_available()` / `suggest_name()`
never raise — a missing package, missing model data, or incompatible spaCy
version just makes `RestructurePlan.ai_available` False and restructuring
falls straight back to the regex-only names it always had. Nothing about
restructuring *requires* the model; it's a quality improvement layered on
top of an already-complete rule-based feature.

**User control:** `Settings.use_ai_suggestions` (default `True`) is a plain
toggle in Preferences; `RestructurePlanWorker(use_ai=...)` reads it. The
wizard's preview page reports how many file names the AI step actually
changed (`RestructurePlan.ai_suggestions_used`), and tells the user plainly
if the model wasn't available on their install — no silent behavior
differences.

**Per-row visibility, not just an aggregate count:** each `PlannedChange`
carries its own `ai_assisted: bool`, set exactly when that row's client name
came from `ner.suggest_name()` rather than the plain regex extraction.
`PreviewPage`'s File-by-File Changes tab shows this as a "✨ AI" marker per
row, so a user can see *which specific files* the AI step actually helped
with, not just a summary number they have to trust.

**No network access ever:** the model ships inside the installer (see
Packaging below); nothing is downloaded or called out to at runtime.

**Why not a generative model:** a full local LLM generating each file's
plan (rather than a NER pass feeding the existing rule-based planner) was
considered and rejected on measured grounds, not assumption — generation is
inherently token-by-token and, even at the smallest usable sizes (~0.5B
params, quantized, CPU-only), takes on the order of 1-6 seconds per file for
a short structured answer. For a 500-file folder that's 8-50 *minutes* to
build a preview, against the few seconds the NER-based approach takes today.
That directly conflicts with restructuring staying fast regardless of
folder size, so `ner.py` stays a single-forward-pass classifier, not a
generator.

**Naming-quality fixes found by testing real messy filenames** (not
assumed — each was reproduced, fixed, and locked in with a test):
- `strip_known_tokens` now strips the *longest* matching keyword first per
  doc-type entry, so `"gst_return_ramesh"` no longer leaves a stray
  `"return"` behind when the shorter `"gst"` keyword eats only part of the
  phrase `"gst return"`.
- `STRUCTURAL_WORDS` and a new `_AUTO_GENERATED_TOKEN_PATTERN` regex now
  catch camera/scanner auto-naming (`IMG_...`, `scan0001`, `Screenshot_...`)
  so these never become a fake "client name" — including the glued-digit
  form (`scan0001`) that a bare word-equality check against `STRUCTURAL_WORDS`
  can't catch on its own.
- `ner.suggest_name()` now title-cases its input before running the model —
  confirmed empirically that `"priya mehta form16 2023"` (as typed in a real
  lowercase filename) finds nothing, while `"Priya Mehta Form16 2023"`
  correctly finds "Priya Mehta". Real filenames are just as often
  all-lowercase or ALL-CAPS as they are Title Case.
- That same title-casing had a side effect: a file's *parent folder name*
  was being fed to the model as extra context, and once title-cased, a
  purely descriptive root/generic folder name (e.g. the user's own selected
  root, or a folder literally called "dump") started reading like a proper
  noun and leaking into the detected name. `plan_restructure` now excludes
  the parent folder from that context when it's the root itself or a
  `STRUCTURAL_WORDS` entry.
- `suggest_name()` prefers a digit-free candidate when the model returns
  multiple entity spans — picking the raw longest string previously let a
  garbled span like `"March2024"` beat a genuine `"Xyz Corp"` match just by
  character count.
- `ner.suggest_name(..., discovered_vocab=...)` now receives the specific
  file's own already-indexed `doc_type` (which may be a category learned
  only for this root via `build_doc_type_vocabulary`, not in the fixed
  CA/finance dictionary), so a loose entity span can't leak a word like
  "Nda" into the name for a folder where "NDA" occurs often enough to have
  been auto-discovered as a category.

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

- `tests/test_metadata_extractor.py` — year/month/doc-type/client
  extraction, plus `build_doc_type_vocabulary` (non-finance category
  discovery, client-token exclusion, flat-folder spread relaxation).
- `tests/test_mismatch.py` — mismatch detection rules.
- `tests/test_indexer_search.py` — end-to-end: scan a temp folder, verify
  index contents, run filtered/free-text searches, verify incremental
  removal of deleted files; plus a synthetic legal-firm tree (zero overlap
  with the CA/finance keyword dictionary) proving doc-type detection
  generalizes.
- `tests/test_restructure.py` — plan generation (full vs rename-only),
  dry-run vs real `apply_plan`, refusal to write outside the root, CSV
  report generation, and a mixed real-documents-plus-actual-git/npm-project
  tree proving the project files are never touched.
- `tests/test_project_detection.py` — marker detection for git/npm/Python/
  etc. projects, and the bottom-up exclusion-set logic on a small tree.
- `tests/test_ner.py` — the entity-cleanup logic (no model needed), plus
  model-backed cases (person/org detection, doc-type/year leakage stripped
  from loose spans) that are skipped rather than failed if the optional NER
  package isn't installed in the current environment.

All of `app/core` is Qt-free, so these run without a display server. The UI
layer was additionally smoke-tested end-to-end (index -> search -> warnings
-> restructure plan -> apply -> re-index) driving the real `QThread` worker
classes under `QT_QPA_PLATFORM=offscreen`. The AI-assist specifically was
verified with a side-by-side plan comparison (`use_ai=False` vs `True`) on
realistic Indian-name filenames, confirming it upgrades e.g.
`.../Priya/...` to `.../Priya_Mehta/...` rather than just trusting that it
would.

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

**Size/time impact of the bundled NER model:** `finder.spec` collects spaCy,
thinc, and the `xx_ent_wiki_sm` model's data files via
`PyInstaller.utils.hooks.collect_all`. On Linux this took the onefile binary
from ~60MB to ~150MB and roughly doubled build time (numpy/blis/spaCy have a
lot of files to scan) — verified with an actual build in this repo's dev
environment, not just estimated. That is the cost of the "Local AI assist"
feature described above; if you build without `spacy`/`xx_ent_wiki_sm`
installed, `collect_all` silently finds nothing, the app still builds and
runs fine, it just always falls back to non-AI restructuring
(`ner.is_available()` returns `False`).

### Known packaging caveat (Linux)

The Qt "xcb" platform plugin PyInstaller bundles depends on the system
having `libxcb-cursor0` (Debian/Ubuntu package name) installed; most desktop
distros already have it via other GTK/Qt apps. If a target machine is
missing it, `apt install libxcb-cursor0` (or the equivalent for that distro)
resolves it. This is a system library, not something PyInstaller can bundle
portably.
