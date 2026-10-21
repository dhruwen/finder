# Finder — User Guide

Finder helps you find files instantly and, if you want, tidy up a messy
folder — without touching anything until you say so.

The app opens to **one page** with everything you'll use day-to-day right on
it: choose a folder, search it, restructure and rename it. Only the
occasional stuff — rebuilding the index, mismatch warnings, preferences —
sits behind the **⚙ Settings** button in the top-right corner. A standard
**File / Edit / View / Help** menu bar is also available (on Windows/Linux
at the top of the window like most desktop apps; on macOS at the very top of
the screen) for keyboard shortcuts and a couple of things that don't need a
page button, like Open Recent — it deliberately doesn't repeat anything
that's already a button on the page, so there's exactly one place to do
each thing.

## 1. Installing

- **Windows:** double-click `FinderSetup-<version>.exe`. It installs in one
  step (no administrator password needed), adds Finder to the Start menu and
  desktop, and offers to launch it. Windows SmartScreen may first show
  "Windows protected your PC" because the installer isn't code-signed yet —
  click **More info -> Run anyway**. To remove it later: Settings -> Apps ->
  Finder -> Uninstall (your settings and indexes are kept).
- **macOS:** open `Finder.app` (or the `.dmg`, then drag it to Applications).
  On first launch, macOS Gatekeeper will refuse to open an app from an
  unidentified developer. Right-click (or Control-click) the app, choose
  **Open**, then confirm **Open** in the dialog. You only need to do this once.
- **Linux:** make the AppImage executable and run it:
  ```bash
  chmod +x Finder-x86_64.AppImage
  ./Finder-x86_64.AppImage
  ```

The app needs no separate database, runtime, or account — it is fully
self-contained and works offline.

## 2. First launch: choose a folder

When you open Finder for the first time, you'll see a **"Choose folder to
search"** button in the middle of the window.

1. Click it and pick the top-level folder you want to search (for example,
   your firm's "Clients" folder).
2. If the folder is large, you'll see an estimate of its size and how much
   disk space the search index needs — confirm to continue.
3. Finder reads every file's **name, path, and basic metadata** (size,
   modified date) under that folder. It never opens or reads the contents of
   your files, and never sends anything over the network.
4. Once the progress bar finishes, the search page appears automatically —
   you're ready to search.

To search a different folder later, click **Change folder…** in the top bar.

## 3. Searching

This is the main page, and it's always just:

- A **search box** at the top — type a name, document type, or any keyword
  (e.g. `John ITR 2024`) and press Enter or click **Search**.
- A **Year** filter right below it. (There's no separate name field: the
  search box already matches the **Detected name** column — the person,
  employee or client Finder found for each file.)
- A **More filters** link that expands to show **File type** — one dropdown
  button per category (Documents, Spreadsheets, Code, Images, Design,
  Archives, …). Only categories that actually have matching files in the
  folder you indexed get a button at all. Click a button to check the
  specific file types you want within that category; the button shows how
  many are selected (e.g. "Code (2) ▾"). Most people will never need to
  open this.

All filters combine together automatically. The line under the results shows
how many files were found and how long the search took.

- **Double-click** a result and Finder asks what you want to do: **Open
  File** (opens it in its default application) or **Open File Location**
  (opens its folder with the file highlighted, so you can find it instantly).
  Tick **"Always do this — don't ask again"** to skip this prompt from then
  on; you can change or reset that choice anytime under **Settings ->
  Preferences -> "When you open a search result"**.
- **Right-click** a result for the same two options without changing your
  remembered default.

## 4. Restructure & Rename

Next to the folder name at the top of the page is a **Restructure & Rename**
button (greyed out until a folder is chosen and indexed). For folders with
inconsistent naming and structure, this wizard reorganizes them for you —
but only after you approve an exact preview:

1. Confirm which folder to restructure (it must already be indexed).
2. Choose a mode: **Full restructure + rename** (moves files into
   `Received/<Year>/<Month>/<Client>/<DocType>/` and renames them to
   `YYYYMMDD_Client_DocType_Description_Version.ext`), or **Rename only,
   keep current folder structure**.
3. Finder analyzes the folder — this step can take a few seconds, since it
   uses a small AI model (running entirely on your computer, never over the
   internet) to help spot full client/employee names in messy file names.
   For example, a file named `Ramesh Kumar Audit FY23-24.pdf` gets correctly
   grouped under "Ramesh Kumar" instead of just "Ramesh". If the AI model
   isn't available on a given install, Finder falls back to its standard
   rules automatically — restructuring always works either way.
4. Review the preview, shown two ways in tabs:
   - **New Folder Structure** — a visual tree of what your folder will look
     like afterward: 📁 for folders (shown in blue if that folder doesn't
     exist yet), a file-type icon for each file (📄 document, 📊 spreadsheet,
     🖼️ image, 💻 code, and so on), a file count next to every folder, and ✨
     next to any file name the AI step improved — so you can see the shape
     of the result at a glance without reading every path.
   - **File-by-File Changes** — the exact old path -> new path for every
     file, with a column marking which names the **AI step actually
     changed** (✨ AI), so you can see exactly where it helped.

   The same file-type icons also appear on the **File type** dropdown
   buttons on the Search page, so folders/files read the same way
   everywhere in the app.

   Above both tabs, a summary shows files/folders affected, any naming
   conflicts (resolved automatically, and shown to you), and how many names
   the AI step improved.
5. Tick the confirmation checkbox and continue — you'll see one more "Are you
   sure?" dialog before anything changes.
6. Watch progress as files move, with any errors listed live.
7. See a plain-language summary, then open the report:
   - **View report** opens an interactive page in your web browser: your
     folder **as it is now** (each file shows what it used to be called or
     where it came from, new folders are marked), your folder **as it was
     before** (each file shows where it went, and old folders that are now
     empty are marked), a searchable list of every change, and any problems.
   - **Open PDF** / **Save PDF as…** gives the same report as a PDF to print
     or share.
   - **Technical log (CSV)** is the raw old path -> new path list.
   All reports are kept in the hidden `.finder_index/reports/` folder inside
   the restructured folder.

Nothing moves until you've seen the full preview and clicked to confirm. All
changes stay strictly inside the folder you selected. You can turn the AI
assist off entirely in Settings -> Preferences if you'd rather it not be used.

**Software project folders are never touched.** If a folder (or any
subfolder) contains `.git`, `package.json`, `requirements.txt`,
`node_modules`, or similar markers, Finder recognizes it as a codebase, not
a document archive, and leaves every file in it exactly where it is — the
preview tells you how many files were skipped this way. If the folder you
picked *is itself* a project, Finder shows a clear explanation and won't let
you proceed at all, rather than silently doing nothing.

### Keep a folder tidy automatically (Auto-rename)

On the last page of the wizard, tick **"Keep this folder tidy"** — or add any
folder under **Settings -> Auto-rename**. From then on, while Finder is open,
every new file added to that folder (or its subfolders) is renamed to match
the naming the folder already uses. There are no rules to write: Finder
learns the convention from the existing files (e.g.
`20240301_Ramesh_ITR_Notes.pdf` -> date, client, document type,
description) and fills it in from the new file's name and the folder it
landed in, so `scan0001.pdf` dropped into `Ramesh/ITR/` becomes
`20241002_Ramesh_ITR.pdf`. If a folder has no consistent naming yet,
Finder's standard naming is used.

- Files are only **renamed, never moved**.
- Partial downloads, hidden files and files still being copied are left
  alone until they're complete.
- A file you rename yourself is never renamed back.
- Every rename appears under **Settings -> Auto-rename -> Recent renames**
  with **Undo**, and in a full log file.
- To use your own naming for a folder, select it and click **Custom
  naming…** (e.g. `{client}_{doctype}_{year}`).

## 5. Menu bar

The menu bar is a second, keyboard-friendly way to reach a few things — it
deliberately does **not** repeat anything that's already a button on the
page (Choose Folder, Restructure & Rename, and Settings all stay
page-only, one way to reach each):

- **File:** **Open Recent** (your last 10 folders, one click to switch — no
  re-indexing needed if it was already indexed before), Rebuild Index, Quit.
- **Edit:** Find (jumps to the search box), Copy File Path (copies the
  selected result's full path), Reset Filters.
- **View:** Refresh Search, More Filters (checkbox stays in sync with the
  on-page "More filters" button either way you toggle it).
- **Help:** User Guide, About Finder.

On macOS, Quit and About move into the **Finder** application menu at the
top of the screen instead of File/Help, matching how every native Mac app
organizes them.

## 6. Settings (everything else)

Click **⚙ Settings** in the top-right corner. It opens a separate window
with three sections, listed on the left:

### Index Management
- See which folders are indexed, when each was last indexed, and how many
  files.
- **Rebuild index** after you've added, removed, or renamed files outside
  Finder, so search stays up to date.
- Switch between multiple indexed folders if you've searched more than one.

### Warnings
Lists files where the folder they're in and the file name itself suggest
*different* clients, document types, or years — for example, a file named
`Suresh_Audit_2023.pdf` sitting inside a `Ramesh/2024/` folder. These are
shown for your review only; Finder never moves them automatically.
Double-click a row to open its folder and check it yourself.

### Preferences
- **Index storage** — by default the index lives in a hidden
  `.finder_index` folder inside the root you selected. If you'd rather store
  it elsewhere (e.g. a faster drive), use **Choose custom location…**, then
  rebuild the index from Index Management.
- **Show mismatch warnings** / **Ask before rebuilding index** — toggle
  these prompts on or off.
- **Use AI-assisted name suggestions during restructuring** — on by default.
  Turn it off to use only the standard rule-based name detection (faster,
  but less accurate on names like "Ramesh Kumar Audit FY23-24" where the
  standard rules would only catch "Ramesh"). This setting shows whether the
  AI model is actually installed on this computer.
- **When you open a search result** — "Ask each time" (default), "Always
  open the file", or "Always open its folder". Matches whatever you last
  chose from the double-click prompt, and you can change it here anytime.
- **About** — version and permissions information.

## 7. Permissions & data notes

- Finder only reads and writes inside the folder(s) you explicitly select,
  plus its own settings/index files.
- It never reads file *contents* — only names, paths, and filesystem
  metadata (size, modified date).
- If a file or folder can't be read (permission error), Finder skips it and
  notes it in the scan summary rather than stopping the whole scan.
- Nothing is ever sent over a network connection.
