from pathlib import Path

from app.core.project_detection import build_project_exclusion_set, is_project_marker_dir


def test_is_project_marker_dir_git(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    assert is_project_marker_dir(tmp_path) is True


def test_is_project_marker_dir_package_json(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}")
    assert is_project_marker_dir(tmp_path) is True


def test_is_project_marker_dir_requirements_txt(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("flask")
    assert is_project_marker_dir(tmp_path) is True


def test_is_project_marker_dir_plain_folder(tmp_path: Path):
    (tmp_path / "Report.pdf").write_text("x")
    assert is_project_marker_dir(tmp_path) is False


def test_build_project_exclusion_set_marks_subtree(tmp_path: Path):
    root = tmp_path
    (root / "Client Files").mkdir()
    proj = root / "delivered_app"
    proj.mkdir()
    (proj / ".git").mkdir()
    src = proj / "src"
    src.mkdir()

    all_dirs = {root / "Client Files", proj, src}
    excluded = build_project_exclusion_set(all_dirs, root)

    assert proj in excluded
    assert src in excluded  # nested inside the project, also excluded
    assert (root / "Client Files") not in excluded


def test_build_project_exclusion_set_no_projects(tmp_path: Path):
    root = tmp_path
    docs = root / "Client Files"
    docs.mkdir()
    excluded = build_project_exclusion_set({docs}, root)
    assert excluded == set()
