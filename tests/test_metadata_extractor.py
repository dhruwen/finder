from app.core.metadata_extractor import (
    build_known_clients,
    extract_client,
    extract_doc_type,
    extract_month,
    extract_year,
)


def test_extract_year_plain():
    assert extract_year("Report_2024_final.pdf") == 2024


def test_extract_year_fy_range():
    assert extract_year("FY23-24 ITR filing") == 2024


def test_extract_year_fy_full():
    assert extract_year("FY2022-2023 Audit") == 2023


def test_extract_year_yyyymmdd():
    assert extract_year("20240315_John_ITR.pdf") == 2024


def test_extract_month_word():
    assert extract_month("Salary_March_2024.xlsx") == 3


def test_extract_month_from_date():
    assert extract_month("20240712_invoice.pdf") == 7


def test_extract_doc_type_itr():
    assert extract_doc_type("John_ITR_2024.pdf") == "ITR"


def test_extract_doc_type_audit():
    assert extract_doc_type("ABC Corp Audit Report 2024") == "Audit"


def test_extract_doc_type_none():
    assert extract_doc_type("randomfile123") is None


def test_extract_client_with_known_list():
    known = ["John Sharma", "ABC Corp"]
    assert extract_client("John_Sharma_ITR_2024.pdf", known) == "John Sharma"


def test_extract_client_fallback_heuristic():
    result = extract_client("XyzCorporation_Invoice_2024.pdf")
    assert result is not None
    assert "xyz" in result.lower() or "corporation" in result.lower()


def test_build_known_clients_filters_structural_words():
    folders = ["Received", "John", "John", "2024", "Audit", "Documents"]
    clients = build_known_clients(folders, min_occurrences=2)
    assert "John" in clients
    assert "Received" not in clients
    assert "2024" not in clients
