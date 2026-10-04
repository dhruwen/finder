from pathlib import Path

from app.core import auto_rename as ar
from app.core.auto_rename import NamingPattern

CLIENTS = ["Ramesh", "John", "Priya", "Acme", "Globex", "Initech"]


def test_learns_structured_convention():
    stems = [
        "20240301_Ramesh_ITR_Acknowledgement",
        "20240401_John_GST_Return_Jan",
        "20230501_Priya_Audit_Notes_v2",
        "20240101_Ramesh_ITR_Computation",
    ]
    p = ar.learn_pattern(stems, CLIENTS)
    assert p is not None
    assert p.template == "{date}_{client}_{doctype}_{description}_{version}"
    assert all(ar.conforms(s, p) for s in stems)
    assert not ar.conforms("scan0001", p)


def test_learns_literal_prefix_separator_and_case():
    p = ar.learn_pattern(["inv-acme-2024", "inv-globex-2023", "inv-initech-2024"], CLIENTS)
    assert p is not None
    assert p.template.startswith("inv-{client}-{year}")
    assert p.case == "lower"
    assert ar.example_for(p) == "inv-ramesh-2024-v2.pdf"


def test_no_convention_in_free_form_names():
    assert ar.learn_pattern(["photo", "resume final", "notes", "cover letter"]) is None
    assert ar.learn_pattern(["20240301_Ramesh_ITR"]) is None  # too few samples


def test_render_drops_empty_slots_and_separators():
    p = NamingPattern("{date}_{client}_{doctype}_{description}_{version}")
    assert ar.render(p, {"date": "20240301", "doctype": "ITR", "description": "Notes"}) == "20240301_ITR_Notes"


def test_ignorable_files():
    for name in ["x.pdf.crdownload", "x.part", ".DS_Store", "~$report.docx", ".hidden"]:
        assert ar.is_ignorable(name)
    assert not ar.is_ignorable("report.pdf")


def test_new_file_takes_client_and_doctype_from_folder(tmp_path: Path):
    root = tmp_path / "Clients"
    itr = root / "Ramesh" / "ITR"
    itr.mkdir(parents=True)
    (root / "John").mkdir()
    for s in ["20240301_Ramesh_ITR_Acknowledgement", "20240401_Ramesh_ITR_Computation", "20230501_Ramesh_ITR_Notes"]:
        (itr / f"{s}.pdf").write_text("x")
    new = itr / "bank statement mar 2024.PDF"
    new.write_text("x")

    vocab = ar.build_folder_vocabulary(root)
    pattern = ar.pattern_for_folder(itr, ar.AUTO, vocab, exclude={new.name})
    assert pattern.learned
    assert ar.propose_name(new, root, pattern, vocab) == "20240301_Ramesh_Bank_Statement.pdf"

    # A known folder client beats a guessed word from the file name.
    echallan = root / "John" / "echallan feb 2024.pdf"
    echallan.write_text("x")
    default = NamingPattern(ar.DEFAULT_TEMPLATE)
    assert ar.propose_name(echallan, root, default, vocab) == "20240201_John_Echallan.pdf"


def test_already_conforming_file_is_left_alone(tmp_path: Path):
    f = tmp_path / "20240301_Ramesh_ITR_Notes.pdf"
    f.write_text("x")
    vocab = ar.FolderVocabulary(["Ramesh"], [])
    assert ar.propose_name(f, tmp_path, NamingPattern(ar.DEFAULT_TEMPLATE), vocab) is None


def test_custom_pattern_and_unique_target(tmp_path: Path):
    (tmp_path / "Ramesh_ITR.pdf").write_text("x")
    assert ar.unique_target(tmp_path, "Ramesh_ITR.pdf").name == "Ramesh_ITR_2.pdf"
    p = ar.pattern_for_folder(tmp_path, "{client}_{doctype}", ar.FolderVocabulary([], []))
    assert p.template == "{client}_{doctype}" and not p.learned
