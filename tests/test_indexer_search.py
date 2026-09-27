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


@pytest.fixture
def legal_firm_root(tmp_path: Path) -> Path:
    """A folder with zero overlap with DOC_TYPE_KEYWORDS (the CA/finance
    dictionary) - proves doc-type detection isn't finance-only."""
    root = tmp_path / "Legal_Data"
    for client in ("Acme Industries", "Beta Holdings", "Gamma LLC"):
        (root / "Clients" / client).mkdir(parents=True)
    (root / "Clients" / "Acme Industries" / "Acme Industries NDA 2024.pdf").write_text("x")
    (root / "Clients" / "Acme Industries" / "Acme Industries Deposition Notes.pdf").write_text("x")
    (root / "Clients" / "Beta Holdings" / "Beta Holdings NDA Jan2024.pdf").write_text("x")
    (root / "Clients" / "Beta Holdings" / "Beta Holdings Deposition Feb2024.pdf").write_text("x")
    (root / "Clients" / "Gamma LLC" / "Gamma LLC NDA March2024.pdf").write_text("x")
    return root


def test_indexer_discovers_doc_types_for_non_finance_domain(legal_firm_root, tmp_path):
    connection = db_mod.connect(tmp_path / "legal_index.sqlite3")
    stats = indexer.scan_root(legal_firm_root, connection)
    assert stats.files_indexed == 5

    assert "Nda" in stats.discovered_doc_types
    assert "Deposition" in stats.discovered_doc_types

    rows = connection.execute(
        "SELECT name, client_name, doc_type FROM files ORDER BY name"
    ).fetchall()
    by_name = {r["name"]: r for r in rows}
    assert by_name["Acme Industries NDA 2024.pdf"]["doc_type"] == "Nda"
    assert by_name["Beta Holdings NDA Jan2024.pdf"]["doc_type"] == "Nda"
    assert by_name["Acme Industries Deposition Notes.pdf"]["doc_type"] == "Deposition"
    # Full multi-word client names, not truncated to the first word.
    assert by_name["Acme Industries NDA 2024.pdf"]["client_name"] == "Acme Industries"
    assert by_name["Beta Holdings NDA Jan2024.pdf"]["client_name"] == "Beta Holdings"

    results = search(connection, SearchFilters(doc_types=["Nda"]))
    assert len(results) == 3
    connection.close()
