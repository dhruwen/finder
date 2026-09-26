from app.core.metadata_extractor import ExtractedMetadata
from app.core.mismatch import detect_mismatch


def test_no_mismatch_when_agree():
    name_meta = ExtractedMetadata(client_name="John", doc_type="ITR", year=2024)
    folder_meta = ExtractedMetadata(client_name="John", doc_type="ITR", year=2024)
    flag, reason = detect_mismatch(name_meta, folder_meta)
    assert flag is False
    assert reason is None


def test_client_mismatch_detected():
    name_meta = ExtractedMetadata(client_name="XYZ", doc_type="ITR", year=2024)
    folder_meta = ExtractedMetadata(client_name="ABC", doc_type="ITR", year=2024)
    flag, reason = detect_mismatch(name_meta, folder_meta)
    assert flag is True
    assert "ABC" in reason and "XYZ" in reason


def test_doc_type_mismatch_detected():
    name_meta = ExtractedMetadata(client_name="John", doc_type="Audit", year=2024)
    folder_meta = ExtractedMetadata(client_name="John", doc_type="ITR", year=2024)
    flag, reason = detect_mismatch(name_meta, folder_meta)
    assert flag is True
    assert "Audit" in reason and "ITR" in reason


def test_year_mismatch_detected():
    name_meta = ExtractedMetadata(client_name="John", doc_type="ITR", year=2023)
    folder_meta = ExtractedMetadata(client_name="John", doc_type="ITR", year=2024)
    flag, reason = detect_mismatch(name_meta, folder_meta)
    assert flag is True
    assert "2023" in reason and "2024" in reason


def test_no_flag_when_one_side_missing_data():
    name_meta = ExtractedMetadata(client_name=None, doc_type="ITR", year=2024)
    folder_meta = ExtractedMetadata(client_name="John", doc_type="ITR", year=2024)
    flag, reason = detect_mismatch(name_meta, folder_meta)
    assert flag is False


def test_no_folder_meta():
    name_meta = ExtractedMetadata(client_name="John", doc_type="ITR", year=2024)
    flag, reason = detect_mismatch(name_meta, None)
    assert flag is False
    assert reason is None


def test_substring_client_not_flagged():
    # "John" is substring of "John Sharma" -> should not be treated as mismatch
    name_meta = ExtractedMetadata(client_name="John", doc_type="ITR", year=2024)
    folder_meta = ExtractedMetadata(client_name="John Sharma", doc_type="ITR", year=2024)
    flag, _ = detect_mismatch(name_meta, folder_meta)
    assert flag is False
