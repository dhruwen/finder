"""SQLite index schema and connection management.

One index database per indexed root. Metadata-only: no file content is ever
stored or read. `files` holds structured columns for fast WHERE-filtering;
`files_fts` is an FTS5 external-content table for bag-of-words search over
name/path/extracted tokens. Phase-2 custom rules can add columns without
touching this module's public API (`connect`, `search`, `upsert_file`, ...).
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    root            TEXT NOT NULL,
    path            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    parent_dir      TEXT NOT NULL,
    extension       TEXT,
    size_bytes      INTEGER,
    modified_at     REAL,
    client_name     TEXT,
    doc_type        TEXT,
    year            INTEGER,
    month           INTEGER,
    folder_client   TEXT,
    folder_doc_type TEXT,
    folder_year     INTEGER,
    folder_month    INTEGER,
    mismatch_flag   INTEGER NOT NULL DEFAULT 0,
    mismatch_reason TEXT,
    indexed_at      REAL NOT NULL,
    UNIQUE(path)
);

CREATE INDEX IF NOT EXISTS idx_files_client ON files(client_name);
CREATE INDEX IF NOT EXISTS idx_files_doctype ON files(doc_type);
CREATE INDEX IF NOT EXISTS idx_files_year ON files(year);
CREATE INDEX IF NOT EXISTS idx_files_month ON files(month);
CREATE INDEX IF NOT EXISTS idx_files_ext ON files(extension);
CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_at);
CREATE INDEX IF NOT EXISTS idx_files_mismatch ON files(mismatch_flag);
CREATE INDEX IF NOT EXISTS idx_files_root ON files(root);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    name, path, client_name, doc_type, tokens,
    content='files', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, name, path, client_name, doc_type, tokens)
    VALUES (new.id, new.name, new.path, new.client_name, new.doc_type,
            coalesce(new.doc_type,'') || ' ' || coalesce(new.client_name,''));
END;

CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, name, path, client_name, doc_type, tokens)
    VALUES ('delete', old.id, old.name, old.path, old.client_name, old.doc_type,
            coalesce(old.doc_type,'') || ' ' || coalesce(old.client_name,''));
END;

CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, name, path, client_name, doc_type, tokens)
    VALUES ('delete', old.id, old.name, old.path, old.client_name, old.doc_type,
            coalesce(old.doc_type,'') || ' ' || coalesce(old.client_name,''));
    INSERT INTO files_fts(rowid, name, path, client_name, doc_type, tokens)
    VALUES (new.id, new.name, new.path, new.client_name, new.doc_type,
            coalesce(new.doc_type,'') || ' ' || coalesce(new.client_name,''));
END;

CREATE TABLE IF NOT EXISTS index_meta (
    root            TEXT PRIMARY KEY,
    last_indexed_at REAL,
    file_count      INTEGER DEFAULT 0,
    total_bytes     INTEGER DEFAULT 0,
    schema_version  INTEGER DEFAULT 1
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def upsert_file(conn: sqlite3.Connection, record: dict) -> None:
    cols = (
        "root", "path", "name", "parent_dir", "extension", "size_bytes",
        "modified_at", "client_name", "doc_type", "year", "month",
        "folder_client", "folder_doc_type", "folder_year", "folder_month",
        "mismatch_flag", "mismatch_reason", "indexed_at",
    )
    values = [record.get(c) for c in cols]
    placeholders = ",".join("?" * len(cols))
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "path")
    conn.execute(
        f"INSERT INTO files ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(path) DO UPDATE SET {updates}",
        values,
    )


def delete_missing_paths(conn: sqlite3.Connection, root: str, seen_paths: set[str]) -> int:
    """Remove indexed rows under `root` whose path was not seen in this scan."""
    cur = conn.execute("SELECT id, path FROM files WHERE root = ?", (root,))
    stale_ids = [row["id"] for row in cur.fetchall() if row["path"] not in seen_paths]
    if stale_ids:
        conn.executemany("DELETE FROM files WHERE id = ?", [(i,) for i in stale_ids])
    return len(stale_ids)


def update_index_meta(conn: sqlite3.Connection, root: str) -> None:
    row = conn.execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(size_bytes),0) AS s FROM files WHERE root = ?",
        (root,),
    ).fetchone()
    conn.execute(
        "INSERT INTO index_meta (root, last_indexed_at, file_count, total_bytes, schema_version) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(root) DO UPDATE SET last_indexed_at=excluded.last_indexed_at, "
        "file_count=excluded.file_count, total_bytes=excluded.total_bytes",
        (root, time.time(), row["c"], row["s"], SCHEMA_VERSION),
    )


def get_index_meta(conn: sqlite3.Connection, root: str) -> dict | None:
    row = conn.execute("SELECT * FROM index_meta WHERE root = ?", (root,)).fetchone()
    return dict(row) if row else None
