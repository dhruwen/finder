"""QThread workers so indexing and file operations never block the UI.

Each worker opens its own SQLite connection (SQLite handles multiple
connections to the same file; WAL mode is enabled in `db.connect`), does its
work, and emits results back to the main thread via signals.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from app.core import db as db_mod
from app.core import indexer, migration
from app.core.restructure import RestructurePlan, plan_restructure


class IndexWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(object)  # IndexStats
    failed = pyqtSignal(str)

    def __init__(self, root: str, db_path: Path):
        super().__init__()
        self.root = root
        self.db_path = db_path
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            conn = db_mod.connect(self.db_path)
            stats = indexer.scan_root(
                Path(self.root),
                conn,
                progress_cb=lambda done, total, path: self.progress.emit(done, total, path),
                cancel_check=lambda: self._cancel,
            )
            conn.close()
            self.finished_ok.emit(stats)
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            self.failed.emit(str(e))


class RestructurePlanWorker(QThread):
    finished_ok = pyqtSignal(object)  # RestructurePlan
    failed = pyqtSignal(str)

    def __init__(self, root: str, db_path: Path, mode: str, use_ai: bool = True):
        super().__init__()
        self.root = root
        self.db_path = db_path
        self.mode = mode
        self.use_ai = use_ai

    def run(self) -> None:
        try:
            conn = db_mod.connect(self.db_path)
            plan = plan_restructure(Path(self.root), conn, mode=self.mode, use_ai=self.use_ai)
            conn.close()
            self.finished_ok.emit(plan)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class RestructureApplyWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(object)  # list[MigrationResult]
    failed = pyqtSignal(str)

    def __init__(self, root: str, db_path: Path, plan: RestructurePlan, dry_run: bool):
        super().__init__()
        self.root = root
        self.db_path = db_path
        self.plan = plan
        self.dry_run = dry_run

    def run(self) -> None:
        try:
            conn = db_mod.connect(self.db_path)
            results = migration.apply_plan(
                self.plan,
                conn,
                Path(self.root),
                dry_run=self.dry_run,
                progress_cb=lambda done, total, path: self.progress.emit(done, total, path),
            )
            conn.close()
            self.finished_ok.emit(results)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
