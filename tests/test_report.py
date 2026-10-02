from pathlib import Path

from app.core import report
from app.core.migration import MigrationResult


def _results(root: Path) -> list[MigrationResult]:
    return [
        MigrationResult(str(root / "a.pdf"), str(root / "20240101_A_ITR.pdf"), 0, "success"),
        MigrationResult(str(root / "old" / "b.pdf"), str(root / "Received" / "2024" / "b.pdf"), 0, "success"),
        MigrationResult(str(root / "old" / "c.pdf"), str(root / "Received" / "2024" / "C_Audit.pdf"), 0, "success"),
        MigrationResult(str(root / "keep" / "d.pdf"), str(root / "Received" / "d.pdf"), 0, "error", "Permission denied"),
    ]


def test_build_report_classifies_changes_and_finds_emptied_folders(tmp_path: Path):
    (tmp_path / "old").mkdir()          # everything moved out of it
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "d.pdf").write_text("x")  # move failed, still there
    data = report.build_report(str(tmp_path), _results(tmp_path), {str(tmp_path / "Received")})

    kinds = {c.old_name: c.kind for c in data.changes}
    assert kinds == {"a.pdf": report.RENAMED, "b.pdf": report.MOVED,
                     "c.pdf": report.MOVED_RENAMED, "d.pdf": report.FAILED}
    assert data.emptied_folders == ["old"]
    assert data.new_folders == ["Received"]


def test_renderers_include_trees_and_problems(tmp_path: Path):
    data = report.build_report(str(tmp_path), _results(tmp_path), {str(tmp_path / "Received"), str(tmp_path / "Received" / "2024")})
    page = report.render_interactive_html(data)
    assert "came from <b>old/b.pdf</b>" in page          # after-tree note
    assert "moved to <b>Received/2024/b.pdf</b>" in page  # before-tree note
    assert "Permission denied" in page
    assert page.count('class="badge new"') == 1           # only top of the new branch

    printable = report.render_print_html(data)
    assert "<script" not in printable
    assert "was a.pdf" in printable and "Permission denied" in printable
