import time
from pathlib import Path

import pytest

from app.core import db as db_mod
from app.core import indexer
from app.core.search import SearchFilters, count, search


@pytest.fixture
def sample_root(tmp_path: Path) -> Path:
    root = tmp_path / "CA_Data"
    (root / "Received" / "2024" / "John").mkdir(parents=True)
    (root / "Received" / "2023" / "ABC_Corp").mkdir(parents=True)
    (root / "Misc").mkdir(parents=True)

    (root / "Received" / "2024" / "John" / "John_ITR_2024.pdf").write_text("dummy")
    (root / "Received" / "2024" / "John" / "John_Salary_March2024.xlsx").write_text("dummy")
    (root / "Received" / "2023" / "ABC_Corp" / "ABC_Audit_2023.pdf").write_text("dummy")
    (root / "Misc" / "randomfile.txt").write_text("dummy")
    return root


@pytest.fixture
def conn(tmp_path: Path, sample_root: Path):
    db_path = tmp_path / "index.sqlite3"
    connection = db_mod.connect(db_path)
    indexer.scan_root(sample_root, connection)
    yield connection
    connection.close()


def test_scan_indexes_all_files(conn):
    row = conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()
    assert row["c"] == 4


def test_search_by_doc_type(conn):
    filters = SearchFilters(doc_types=["ITR"])
    results = search(conn, filters)
    assert len(results) == 1
    assert "ITR" in results[0]["name"]


def test_search_by_extension(conn):
    filters = SearchFilters(extensions=["pdf"])
    results = search(conn, filters)
    assert len(results) == 2
    assert count(conn, filters) == 2


def test_search_by_year(conn):
    filters = SearchFilters(year=2023)
    results = search(conn, filters)
    assert len(results) == 1
    assert "ABC" in results[0]["name"]


def test_search_free_text(conn):
    filters = SearchFilters(text="salary")
    results = search(conn, filters)
    assert len(results) == 1
    assert "Salary" in results[0]["name"]


def test_search_combined_filters(conn):
    filters = SearchFilters(client_name="John", extensions=["pdf"])
    results = search(conn, filters)
    assert len(results) == 1
    assert results[0]["name"] == "John_ITR_2024.pdf"


def test_incremental_removes_deleted_files(sample_root, tmp_path):
    db_path = tmp_path / "index2.sqlite3"
    connection = db_mod.connect(db_path)
    indexer.scan_root(sample_root, connection)
    assert connection.execute("SELECT COUNT(*) AS c FROM files").fetchone()["c"] == 4

    (sample_root / "Misc" / "randomfile.txt").unlink()
    stats = indexer.scan_root(sample_root, connection)
    assert stats.files_removed == 1
    assert connection.execute("SELECT COUNT(*) AS c FROM files").fetchone()["c"] == 3
    connection.close()
