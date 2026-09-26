# Finder — User Guide

Finder helps you find files instantly and, if you want, tidy up a messy
folder — without touching anything until you say so.

The app opens to **one page**: choose a folder, then search it. Everything
else lives behind the **⚙ Settings** button in the top-right corner, so you
only need to go there if you want to rebuild the index, reorganize files, or
check settings.

## 1. Installing

- **Windows:** run `Finder.exe`. No other install is required. On first
  launch, Windows SmartScreen may show "Windows protected your PC" because
  the app isn't yet code-signed — click **More info -> Run anyway**.
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

- A **search box** at the top — type a client name, document type, or any
  keyword (e.g. `John ITR 2024`) and press Enter or click **Search**.
- Three quick filters right below it: **Client**, **Document type**, and
  **Year** — set any of these to narrow results further.
- A **More filters** link that expands to show Month, a date range (with
  quick buttons like **This year** or **Past 3 mo**), file type (PDF, Excel,
  Word, …), a folder-path filter, and an option to show only
  possibly-misplaced files. Most people will never need to open this.

All filters combine together automatically. The line under the results shows
how many files were found and how long the search took.

- **Double-click** a result to open it in its default application.
- **Right-click** a result for options to open the file or reveal its folder.

## 4. Settings (everything else)

Click **⚙ Settings** in the top-right corner. It opens a separate window
with four sections, listed on the left:

### Index Management
- See which folders are indexed, when each was last indexed, and how many
  files.
- **Rebuild index** after you've added, removed, or renamed files outside
  Finder, so search stays up to date.
- Switch between multiple indexed folders if you've searched more than one.

### Restructure & Rename
For folders with inconsistent naming and structure, this wizard reorganizes
them for you — but only after you approve an exact preview:

1. Confirm which folder to restructure (it must already be indexed).
2. Choose a mode: **Full restructure + rename** (moves files into
   `Received/<Year>/<Month>/<Client>/<DocType>/` and renames them to
   `YYYYMMDD_Client_DocType_Description_Version.ext`), or **Rename only,
   keep current folder structure**.
3. Review the full **old path -> new path** preview for every file, plus a
   summary of files/folders affected and any naming conflicts (resolved
   automatically, and shown to you).
4. Tick the confirmation checkbox and continue — you'll see one more "Are you
   sure?" dialog before anything changes.
5. Watch progress as files move, with any errors listed live.
6. See a summary and open the **migration report** — a CSV of every old
   path, new path, and result, saved inside the folder under
   `.finder_index/reports/`.

Nothing moves until you've seen the full preview and clicked to confirm. All
changes stay strictly inside the folder you selected.

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
- **About** — version and permissions information.

## 5. Permissions & data notes

- Finder only reads and writes inside the folder(s) you explicitly select,
  plus its own settings/index files.
- It never reads file *contents* — only names, paths, and filesystem
  metadata (size, modified date).
- If a file or folder can't be read (permission error), Finder skips it and
  notes it in the scan summary rather than stopping the whole scan.
- Nothing is ever sent over a network connection.
