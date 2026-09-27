"""Search query construction and execution.

All filters combine with AND. Free text goes through the FTS5 index; every
other filter is a plain indexed WHERE clause. No query language is exposed to
the user — the UI only ever builds a `SearchFilters` object.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class SearchFilters:
    text: str = ""
    client_name: str = ""
    doc_types: list[str] = field(default_factory=list)
    year: int | None = None
    month: int | None = None
    date_from: float | None = None  # epoch seconds, from modified_at
    date_to: float | None = None
    extensions: list[str] = field(default_factory=list)
    path_pattern: str = ""  # glob-ish, e.g. "Received/2024/*"
    only_mismatches: bool = False
    root: str | None = None


QUICK_RANGES = {
    "this_month": lambda now: (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now),
    "past_3_months": lambda now: (now - timedelta(days=90), now),
    "past_1_year": lambda now: (now - timedelta(days=365), now),
    "this_year": lambda now: (now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), now),
}


def resolve_quick_range(key: str, now: datetime | None = None) -> tuple[float, float]:
    now = now or datetime.now()
    start, end = QUICK_RANGES[key](now)
    return start.timestamp(), end.timestamp()


def _fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression (AND of prefix terms)."""
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    if not tokens:
        return ""
    return " AND ".join(f'"{t}"*' for t in tokens)


def _path_pattern_to_like(pattern: str) -> str:
    """Translate a simple 'a/b/*' style pattern into a SQL LIKE pattern."""
    like = pattern.replace("%", r"\%").replace("_", r"\_")
    like = like.replace("*", "%")
    if not like.startswith("%"):
        like = "%" + like
    if not like.endswith("%"):
        like = like + "%"
    return like


def build_query(filters: SearchFilters) -> tuple[str, list]:
    select = "SELECT f.* FROM files f"
    joins = []
    where = []
    params: list = []

    fts = _fts_query(filters.text) if filters.text.strip() else ""
    if fts:
        joins.append("JOIN files_fts ON files_fts.rowid = f.id")
        where.append("files_fts MATCH ?")
        params.append(fts)

    if filters.root:
        where.append("f.root = ?")
        params.append(filters.root)

    if filters.client_name.strip():
        where.append("f.client_name LIKE ?")
        params.append(f"%{filters.client_name.strip()}%")

    if filters.doc_types:
        placeholders = ",".join("?" * len(filters.doc_types))
        where.append(f"f.doc_type IN ({placeholders})")
        params.extend(filters.doc_types)

    if filters.year is not None:
        where.append("f.year = ?")
        params.append(filters.year)

    if filters.month is not None:
        where.append("f.month = ?")
        params.append(filters.month)

    if filters.date_from is not None:
        where.append("f.modified_at >= ?")
        params.append(filters.date_from)

    if filters.date_to is not None:
        where.append("f.modified_at <= ?")
        params.append(filters.date_to)

    if filters.extensions:
        norm = [e.lower().lstrip(".") for e in filters.extensions]
        placeholders = ",".join("?" * len(norm))
        where.append(f"f.extension IN ({placeholders})")
        params.extend(norm)

    if filters.path_pattern.strip():
        where.append("f.path LIKE ? ESCAPE '\\'")
        params.append(_path_pattern_to_like(filters.path_pattern.strip()))

    if filters.only_mismatches:
        where.append("f.mismatch_flag = 1")

    sql = select + (" " + " ".join(joins) if joins else "")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY f.modified_at DESC"
    return sql, params


def search(
    conn: sqlite3.Connection, filters: SearchFilters, limit: int = 1000, offset: int = 0
) -> list[sqlite3.Row]:
    sql, params = build_query(filters)
    sql += " LIMIT ? OFFSET ?"
    params = params + [limit, offset]
    return conn.execute(sql, params).fetchall()


def count(conn: sqlite3.Connection, filters: SearchFilters) -> int:
    sql, params = build_query(filters)
    wrapped = f"SELECT COUNT(*) AS c FROM ({sql})"
    return conn.execute(wrapped, params).fetchone()["c"]


def list_distinct_doc_types(conn: sqlite3.Connection, root: str | None = None) -> list[str]:
    if root:
        rows = conn.execute(
            "SELECT DISTINCT doc_type FROM files WHERE root=? AND doc_type IS NOT NULL ORDER BY doc_type",
            (root,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT doc_type FROM files WHERE doc_type IS NOT NULL ORDER BY doc_type"
        ).fetchall()
    return [r["doc_type"] for r in rows]


def list_distinct_extensions(conn: sqlite3.Connection, root: str | None = None) -> list[str]:
    """Every file extension actually present in the index (not a hardcoded list)."""
    if root:
        rows = conn.execute(
            "SELECT DISTINCT extension FROM files WHERE root=? AND extension IS NOT NULL "
            "AND extension != '' ORDER BY extension",
            (root,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT extension FROM files WHERE extension IS NOT NULL AND extension != '' "
            "ORDER BY extension"
        ).fetchall()
    return [r["extension"] for r in rows]


def list_distinct_years(conn: sqlite3.Connection, root: str | None = None) -> list[int]:
    if root:
        rows = conn.execute(
            "SELECT DISTINCT year FROM files WHERE root=? AND year IS NOT NULL ORDER BY year DESC",
            (root,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT year FROM files WHERE year IS NOT NULL ORDER BY year DESC"
        ).fetchall()
    return [r["year"] for r in rows]
