from pathlib import Path

import pytest

from app.core import db as db_mod, ner
from app.core import indexer, migration
from app.core.restructure import plan_restructure


@pytest.fixture
def messy_root(tmp_path: Path) -> Path:
    root = tmp_path / "Messy"
    (root / "stuff").mkdir(parents=True)
    (root / "stuff2").mkdir(parents=True)
    (root / "stuff" / "johnitr24.pdf").write_text("dummy")
    (root / "stuff2" / "abc_audit_2023_final.pdf").write_text("dummy")
    return root


@pytest.fixture
def conn(tmp_path, messy_root):
    connection = db_mod.connect(tmp_path / "idx.sqlite3")
    indexer.scan_root(messy_root, connection)
    yield connection
    connection.close()


def test_plan_moves_into_canonical_structure(conn, messy_root):
    plan = plan_restructure(messy_root, conn, mode="full")
    assert plan.files_affected == 2
    for change in plan.changes:
        assert "Received" in change.new_path
        assert change.new_path.startswith(str(messy_root))


def test_plan_new_folders_includes_full_ancestor_chain(conn, messy_root):
    # Every directory level of a brand-new "Received/<Year>/<Month>/<Client>/
    # <DocType>" chain should be tracked as new, not just the deepest one -
    # otherwise a UI highlighting "new" folders would only mark the last
    # segment and leave its parents looking pre-existing.
    plan = plan_restructure(messy_root, conn, mode="full")
    for change in plan.changes:
        new_dir = Path(change.new_path).parent
        while new_dir != messy_root:
            assert str(new_dir) in plan.new_folders, f"{new_dir} missing from new_folders"
            new_dir = new_dir.parent


def test_plan_rename_only_keeps_folder(conn, messy_root):
    plan = plan_restructure(messy_root, conn, mode="rename_only")
    for change in plan.changes:
        old_dir = str(Path(change.old_path).parent)
        new_dir = str(Path(change.new_path).parent)
        assert old_dir == new_dir


def test_apply_plan_dry_run_does_not_touch_disk(conn, messy_root):
    plan = plan_restructure(messy_root, conn, mode="full")
    results = migration.apply_plan(plan, conn, messy_root, dry_run=True)
    assert all(r.status == "dry_run" for r in results)
    # original files still exist
    assert (messy_root / "stuff" / "johnitr24.pdf").exists()


def test_apply_plan_moves_files(conn, messy_root):
    plan = plan_restructure(messy_root, conn, mode="full")
    results = migration.apply_plan(plan, conn, messy_root, dry_run=False)
    assert all(r.status == "success" for r in results)
    for r in results:
        assert Path(r.new_path).exists()
        assert not Path(r.old_path).exists()


def test_apply_plan_refuses_outside_root(conn, messy_root, tmp_path):
    plan = plan_restructure(messy_root, conn, mode="full")
    # tamper with one change to point outside the root
    outside = tmp_path / "outside.pdf"
    plan.changes[0].new_path = str(outside)
    results = migration.apply_plan(plan, conn, messy_root, dry_run=False)
    tampered = [r for r in results if r.new_path == str(outside)][0]
    assert tampered.status == "error"
    assert not outside.exists()


def test_write_report_csv(tmp_path, conn, messy_root):
    plan = plan_restructure(messy_root, conn, mode="full")
    results = migration.apply_plan(plan, conn, messy_root, dry_run=True)
    report_path = migration.write_report(results, tmp_path / "report.csv", fmt="csv")
    assert report_path.exists()
    content = report_path.read_text()
    assert "old_path" in content and "new_path" in content


@pytest.fixture
def mixed_root_with_project(tmp_path: Path) -> Path:
    """A root with real documents alongside an actual git/npm project -
    restructuring must touch the documents but never the project files."""
    root = tmp_path / "Mixed"
    (root / "Client Files" / "Ramesh").mkdir(parents=True)
    (root / "Client Files" / "Ramesh" / "Ramesh Audit 2024.pdf").write_text("dummy")

    proj = root / "delivered_app"
    (proj / "src").mkdir(parents=True)
    (proj / ".git").mkdir()
    (proj / "package.json").write_text("{}")
    (proj / "src" / "index.js").write_text("console.log(1)")
    return root


def test_plan_never_touches_software_project_files(tmp_path, mixed_root_with_project):
    connection = db_mod.connect(tmp_path / "mixed_idx.sqlite3")
    indexer.scan_root(mixed_root_with_project, connection)

    plan = plan_restructure(mixed_root_with_project, connection, mode="full", use_ai=False)

    assert plan.files_affected == 1
    assert plan.skipped_project_files == 2  # package.json + src/index.js
    assert plan.root_is_project is False
    assert all("delivered_app" not in c.old_path for c in plan.changes)
    connection.close()


def test_plan_refuses_when_root_itself_is_a_project(tmp_path):
    root = tmp_path / "SomeRepo"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "requirements.txt").write_text("flask")
    (root / "app.py").write_text("print(1)")

    connection = db_mod.connect(tmp_path / "repo_idx.sqlite3")
    indexer.scan_root(root, connection)

    plan = plan_restructure(root, connection, mode="full", use_ai=False)

    assert plan.root_is_project is True
    assert plan.files_affected == 0
    assert plan.skipped_project_files > 0
    connection.close()


@pytest.mark.skipif(not ner.is_available(), reason="NER model package not installed in this environment")
def test_ai_client_name_never_includes_root_or_generic_folder_name(tmp_path):
    # A descriptive root folder name (or a generic "dump"/"Misc" subfolder)
    # must never get swept into the AI-detected client name just because
    # it's sitting next to the file - only the file's own name, and a
    # genuinely meaningful parent folder, should contribute.
    root = tmp_path / "Some_Descriptive_Root_Folder_Name"
    root.mkdir()
    (root / "Ramesh Kumar Audit FY23-24.pdf").write_text("x")
    (root / "dump").mkdir()
    (root / "dump" / "Priya Mehta Form16 2023.pdf").write_text("x")

    connection = db_mod.connect(tmp_path / "idx.sqlite3")
    indexer.scan_root(root, connection)
    plan = plan_restructure(root, connection, mode="full", use_ai=True)

    for change in plan.changes:
        # Check only the generated portion (client/doctype/filename segments),
        # not the full absolute path - the root's own folder name naturally
        # appears as a path prefix and isn't what this test is about.
        generated = str(Path(change.new_path).relative_to(root)).lower()
        assert "descriptive" not in generated
        assert "root_folder" not in generated
        assert "dump" not in generated
    connection.close()
