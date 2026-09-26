"""Filesystem walker that builds/refreshes the metadata index.

Two passes over the tree:
  1. Collect folder names (cheap) to build a client-name vocabulary.
  2. Walk files, extract metadata, stat, and upsert into SQLite.

Permission errors on individual files/folders are caught and logged, never
raised — the scan continues. Nothing outside the selected root is touched or
read (file *contents* are never read at all, only names/paths/stat info).
"""
from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.core import db as db_mod
from app.core.metadata_extractor import build_known_clients, extract_all
from app.core.mismatch import detect_mismatch

# Folders we never descend into: index metadata, VCS internals, OS junk.
SKIP_DIR_NAMES = {".finder_index", ".git", ".svn", "__pycache__", ".DS_Store", "$RECYCLE.BIN", "System Volume Information"}


@dataclass
class IndexStats:
    files_indexed: int = 0
    files_removed: int = 0
    folders_seen: int = 0
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    mismatches: int = 0


ProgressCallback = Callable[[int, int, str], None]  # (done, total_estimate, current_path)


def _iter_dirnames(root: Path) -> list[str]:
    names: list[str] = []
    for dirpath, dirnames, _filenames in os.walk(root, onerror=lambda e: None):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        names.extend(dirnames)
    return names


def scan_root(
    root: Path,
    conn: sqlite3.Connection,
    progress_cb: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> IndexStats:
    """Full (re)index of `root`. Adds/updates files, removes ones that vanished."""
    start = time.time()
    stats = IndexStats()
    root = root.resolve()
    root_str = str(root)

    known_clients = build_known_clients(_iter_dirnames(root))

    seen_paths: set[str] = set()
    done = 0
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: stats.errors.append(str(e))):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        stats.folders_seen += 1
        rel_dir = os.path.relpath(dirpath, root)
        folder_text = rel_dir if rel_dir != "." else ""
        folder_meta = extract_all(folder_text, known_clients) if folder_text else None

        for fname in filenames:
            if cancel_check and cancel_check():
                stats.elapsed_seconds = time.time() - start
                return stats
            fpath = Path(dirpath) / fname
            try:
                st = fpath.stat()
            except OSError as e:
                stats.errors.append(f"{fpath}: {e}")
                continue

            name_meta = extract_all(fpath.stem, known_clients)
            ext = fpath.suffix.lower().lstrip(".")

            mismatch_flag, mismatch_reason = detect_mismatch(name_meta, folder_meta)
            if mismatch_flag:
                stats.mismatches += 1

            record = {
                "root": root_str,
                "path": str(fpath),
                "name": fname,
                "parent_dir": dirpath,
                "extension": ext,
                "size_bytes": st.st_size,
                "modified_at": st.st_mtime,
                "client_name": name_meta.client_name or (folder_meta.client_name if folder_meta else None),
                "doc_type": name_meta.doc_type or (folder_meta.doc_type if folder_meta else None),
                "year": name_meta.year or (folder_meta.year if folder_meta else None),
                "month": name_meta.month or (folder_meta.month if folder_meta else None),
                "folder_client": folder_meta.client_name if folder_meta else None,
                "folder_doc_type": folder_meta.doc_type if folder_meta else None,
                "folder_year": folder_meta.year if folder_meta else None,
                "folder_month": folder_meta.month if folder_meta else None,
                "mismatch_flag": 1 if mismatch_flag else 0,
                "mismatch_reason": mismatch_reason,
                "indexed_at": time.time(),
            }
            try:
                db_mod.upsert_file(conn, record)
            except sqlite3.Error as e:
                stats.errors.append(f"{fpath}: db error {e}")
                continue
            seen_paths.add(str(fpath))
            stats.files_indexed += 1
            done += 1
            if progress_cb and done % 50 == 0:
                progress_cb(done, done, str(fpath))

    stats.files_removed = db_mod.delete_missing_paths(conn, root_str, seen_paths)
    db_mod.update_index_meta(conn, root_str)
    conn.commit()
    stats.elapsed_seconds = time.time() - start
    if progress_cb:
        progress_cb(done, done, "")
    return stats


def incremental_refresh(
    root: Path,
    conn: sqlite3.Connection,
    progress_cb: ProgressCallback | None = None,
) -> IndexStats:
    """Refresh only files whose mtime changed or that are new; still detects deletions.

    For Phase-1 this reuses the full-scan logic (upsert is idempotent and cheap
    relative to a full disk walk, which dominates cost either way), but skips
    re-stat work is not worth the complexity yet. Kept as a separate entry
    point so Phase-2 can optimize (e.g. mtime-based directory skipping).
    """
    return scan_root(root, conn, progress_cb)
