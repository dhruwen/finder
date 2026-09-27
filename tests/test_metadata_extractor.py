from app.core.metadata_extractor import (
    build_doc_type_vocabulary,
    build_known_clients,
    extract_client,
    extract_doc_type,
    extract_month,
    extract_year,
    extension_category,
    month_label,
    normalize_extension,
    strip_known_tokens,
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


def test_extract_month_never_returns_invalid_value_for_us_style_dates():
    # "03-14-2024" can only be MM-DD (March 14) - 14 is not a valid month.
    # A naive DD-MM assumption would previously store month=14.
    assert extract_month("invoice_03-14-2024") == 3
    assert extract_month("report_12-25-2023") == 12
    assert extract_month("notes_07-31-2024") == 7
    for text in ["invoice_03-14-2024", "report_12-25-2023", "notes_07-31-2024"]:
        month = extract_month(text)
        assert month is None or 1 <= month <= 12


def test_extract_month_dd_mm_still_preferred_when_both_readings_valid():
    # "12-03-2022" is ambiguous (could be 12-Mar or Dec-3); DD-MM is this
    # app's primary convention, so month should resolve to March (3).
    assert extract_month("xyz invoice 12-03-2022") == 3


def test_extract_year_rejects_impossible_yyyymmdd():
    # "invoice-2024-99-14" isn't a real date (month 99) - the year should
    # still resolve via the plain 4-digit-year fallback, but no bogus month
    # should ever come from the rejected YYYYMMDD reading.
    assert extract_year("invoice-2024-99-14") == 2024
    assert extract_month("invoice-2024-99-14") is None


def test_month_label():
    assert month_label(3) == "Mar"
    assert month_label(12) == "Dec"
    assert month_label(None) == ""
    assert month_label(14) == ""
    assert month_label(0) == ""


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


def test_normalize_extension_recognizes_real_extensions():
    assert normalize_extension(".pdf") == "pdf"
    assert normalize_extension(".DOCX") == "docx"
    assert normalize_extension("xlsx") == "xlsx"


def test_normalize_extension_rejects_version_fragments():
    # "Ramesh Audit FY22-23.v2" -> suffix ".v2" is not a real file extension.
    assert normalize_extension(".v2") is None
    # "GST Return.Jan.2024" -> last suffix ".2024" is a year, not an extension.
    assert normalize_extension(".2024") is None
    # "scan.1" -> purely numeric fragment.
    assert normalize_extension(".1") is None
    # "Report.Final" -> descriptive word, not a real file type.
    assert normalize_extension(".final") is None


def test_normalize_extension_handles_no_extension():
    assert normalize_extension("") is None


def test_normalize_extension_covers_non_finance_file_types():
    # A curated allowlist of only CA/finance-relevant extensions would
    # silently hide every one of these for any other corporate domain
    # (engineering, design, software, media) - they must all resolve.
    for ext, expected in [
        (".dwg", "dwg"), (".psd", "psd"), (".py", "py"), (".sql", "sql"),
        (".cdr", "cdr"), (".ai", "ai"), (".js", "js"), (".yaml", "yaml"),
        (".mkv", "mkv"), (".epub", "epub"), (".md", "md"), (".svg", "svg"),
    ]:
        assert normalize_extension(ext) == expected, f"{ext} should resolve, not be hidden"


def test_extension_category_groups_across_domains():
    assert extension_category("pdf") == "Documents"
    assert extension_category("docx") == "Documents"
    assert extension_category("xlsx") == "Spreadsheets"
    assert extension_category("csv") == "Spreadsheets"
    assert extension_category("pptx") == "Presentations"
    assert extension_category("png") == "Images"
    assert extension_category("svg") == "Images"
    assert extension_category("psd") == "Design"
    assert extension_category("dwg") == "Design"
    assert extension_category("py") == "Code"
    assert extension_category("js") == "Code"
    assert extension_category("zip") == "Archives"
    assert extension_category("mp4") == "Audio/Video"
    assert extension_category("msg") == "Email"


def test_extension_category_unknown_extension_falls_back_gracefully():
    # Never crashes, never returns something outside the fixed category set.
    from app.core.metadata_extractor import CATEGORY_ORDER
    assert extension_category("totallymadeupext") in CATEGORY_ORDER


def test_normalize_extension_still_rejects_version_and_status_words():
    # The broadened coverage above must not reopen the original bug: stray
    # version/status fragments should still never be treated as extensions.
    for ext in [".v2", ".v23", ".23", ".final", ".draft", ".old", ".2024", ".1", ".signed"]:
        assert normalize_extension(ext) is None, f"{ext} should NOT resolve to an extension"


def test_build_doc_type_vocabulary_learns_non_finance_categories():
    # A legal firm's files: "NDA" and "Deposition" repeat across different
    # clients (should be discovered as categories), "Renewal" appears once
    # (should NOT be discovered - looks like a one-off description word).
    entries = [
        ("Acme Industries NDA 2024", "Acme Industries"),
        ("Acme Industries Deposition Notes", "Acme Industries"),
        ("Beta Holdings NDA Jan2024", "Beta Holdings"),
        ("Beta Holdings Deposition Feb2024", "Beta Holdings"),
        ("Gamma LLC NDA March", "Gamma LLC"),
        ("Gamma LLC Contract Renewal 2024", "Gamma LLC"),
    ]
    known_clients = ["Acme Industries", "Beta Holdings", "Gamma LLC"]
    vocab = build_doc_type_vocabulary(entries, known_clients, min_doc_frequency=2, min_spread=2)
    assert "Nda" in vocab
    assert "Deposition" in vocab
    assert "Renewal" not in vocab  # only appears once, and in a single client's folder


def test_build_doc_type_vocabulary_excludes_client_name_tokens():
    # "Memo" is used because it is NOT in DOC_TYPE_KEYWORDS - words already in
    # the fixed dictionary are deliberately excluded from candidacy (they're
    # already handled by extract_doc_type's first pass, so re-discovering
    # them would be redundant).
    entries = [
        ("Acme Industries Memo 2024", "Acme Industries"),
        ("Acme Industries Memo 2023", "Acme Industries"),
        ("Beta Holdings Memo 2024", "Beta Holdings"),
    ]
    known_clients = ["Acme Industries", "Beta Holdings"]
    vocab = build_doc_type_vocabulary(entries, known_clients, min_doc_frequency=2, min_spread=2)
    assert "Acme" not in vocab
    assert "Industries" not in vocab
    assert "Memo" in vocab


def test_build_doc_type_vocabulary_flat_folder_relaxes_spread():
    # No subfolders at all (every file's parent is the same folder) - spread
    # can't discriminate here, so frequency alone should still work.
    # "Timesheet" is used because it is NOT in DOC_TYPE_KEYWORDS.
    entries = [
        ("Timesheet January", "root"),
        ("Timesheet February", "root"),
        ("Timesheet March", "root"),
    ]
    vocab = build_doc_type_vocabulary(entries, None, min_doc_frequency=2, min_spread=2)
    assert "Timesheet" in vocab


def test_extract_doc_type_falls_back_to_discovered_vocab():
    assert extract_doc_type("Acme Industries NDA 2024", discovered_vocab=["Nda", "Deposition"]) == "Nda"
    assert extract_doc_type("something unrelated", discovered_vocab=["Nda"]) is None


def test_strip_known_tokens_removes_longest_keyword_first():
    # "gst" alone must not eat only part of "gst return" and leave "return"
    # behind as a stray word that used to get mistaken for part of a name.
    tokens = strip_known_tokens("gst_return_ramesh")
    assert "return" not in tokens
    assert tokens == ["ramesh"]


def test_strip_known_tokens_removes_auto_generated_camera_prefixes():
    # "scan0001", "img2024" etc. are camera/scanner auto-naming, not a
    # client name, even though the bare word "scan"/"img" wouldn't match
    # these once a sequence number is glued on with no separator.
    assert strip_known_tokens("scan0001") == []
    assert strip_known_tokens("img2024") == []
    assert strip_known_tokens("IMG_20240315_142233") == []


def test_extract_client_ignores_auto_generated_camera_filenames():
    assert extract_client("scan0001") is None
    assert extract_client("IMG_20240315_142233") is None
