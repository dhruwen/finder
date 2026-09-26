from pathlib import Path

import pytest

from app.core import db as db_mod
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
