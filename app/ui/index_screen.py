"""Index Management screen: select a root, (re)build the index, view stats."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QProgressBar, QGroupBox, QFormLayout, QMessageBox,
    QFileDialog,
)
from PyQt6.QtCore import Qt

from app.core import db as db_mod
from app.core.size_estimate import estimate, format_confirmation_message
from app.ui.app_state import AppState
from app.ui.workers import IndexWorker


class IndexScreen(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._worker: IndexWorker | None = None
        self._build_ui()
        self._refresh_roots_list()
        self._refresh_stats()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Index Management")
        title.setObjectName("screenTitle")
        layout.addWidget(title)

        btn_row = QHBoxLayout()
        select_btn = QPushButton("Select root folder…")
        select_btn.clicked.connect(self.select_root)
        self.rebuild_btn = QPushButton("Rebuild index")
        self.rebuild_btn.clicked.connect(self.rebuild_index)
        btn_row.addWidget(select_btn)
        btn_row.addWidget(self.rebuild_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        roots_group = QGroupBox("Indexed roots")
        roots_layout = QVBoxLayout(roots_group)
        self.roots_list = QListWidget()
        self.roots_list.itemClicked.connect(self._on_root_selected)
        roots_layout.addWidget(self.roots_list)
        layout.addWidget(roots_group)

        stats_group = QGroupBox("Current index stats")
        self.stats_form = QFormLayout(stats_group)
        self.stat_root = QLabel("—")
        self.stat_root.setWordWrap(True)
        self.stat_files = QLabel("—")
        self.stat_size = QLabel("—")
        self.stat_last_indexed = QLabel("—")
        self.stats_form.addRow("Root:", self.stat_root)
        self.stats_form.addRow("Files indexed:", self.stat_files)
        self.stats_form.addRow("Total size:", self.stat_size)
        self.stats_form.addRow("Last indexed:", self.stat_last_indexed)
        layout.addWidget(stats_group)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.progress_label = QLabel("")
        layout.addWidget(self.progress_label)

        layout.addStretch(1)

    def _refresh_roots_list(self) -> None:
        self.roots_list.clear()
        for root in self.state.settings.roots:
            item = QListWidgetItem(root)
            if root == self.state.current_root:
                item.setSelected(True)
            self.roots_list.addItem(item)

    def _on_root_selected(self, item: QListWidgetItem) -> None:
        self.state.set_root(item.text())
        self._refresh_stats()
        self.state.notify_index_changed()

    def select_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select folder to index")
        if not directory:
            return

        est = estimate(Path(directory))
        if est.file_count > 2000 or est.total_bytes > 500 * 1024 * 1024:
            msg = format_confirmation_message(est)
            reply = QMessageBox.question(
                self, "Confirm indexing", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.state.set_root(directory)
        self._refresh_roots_list()
        self._refresh_stats()
        self.rebuild_index()

    def rebuild_index(self) -> None:
        if not self.state.current_root:
            QMessageBox.information(self, "No folder selected", "Select a root folder first.")
            return
        if self.state.settings.ask_before_rebuild:
            reply = QMessageBox.question(
                self, "Rebuild index",
                f"Rebuild the search index for:\n{self.state.current_root}\n\n"
                "This reads file names and metadata only (never file contents).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.rebuild_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress_label.setText("Scanning…")

        db_path = self.state.settings.index_path_for(self.state.current_root)
        self._worker = IndexWorker(self.state.current_root, db_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_index_finished)
        self._worker.failed.connect(self._on_index_failed)
        self._worker.start()

    def _on_progress(self, done: int, total: int, path: str) -> None:
        self.progress_label.setText(f"Indexed {done} files… {path}")

    def _on_index_finished(self, stats) -> None:
        self.progress.setVisible(False)
        self.rebuild_btn.setEnabled(True)
        self.progress_label.setText(
            f"Done: {stats.files_indexed} files indexed, {stats.files_removed} removed, "
            f"{stats.mismatches} possibly misplaced, {len(stats.errors)} errors, "
            f"{stats.elapsed_seconds:.1f}s."
        )
        # Reopen the shared connection so other screens see fresh data.
        self.state.set_root(self.state.current_root)
        self._refresh_stats()
        self.state.notify_index_changed()

    def _on_index_failed(self, error: str) -> None:
        self.progress.setVisible(False)
        self.rebuild_btn.setEnabled(True)
        QMessageBox.critical(self, "Indexing failed", error)

    def _refresh_stats(self) -> None:
        if not self.state.current_root or not self.state.conn:
            self.stat_root.setText("No folder selected")
            self.stat_files.setText("—")
            self.stat_size.setText("—")
            self.stat_last_indexed.setText("—")
            return
        meta = db_mod.get_index_meta(self.state.conn, self.state.current_root)
        self.stat_root.setText(self.state.current_root)
        if meta:
            self.stat_files.setText(f"{meta['file_count']:,}")
            self.stat_size.setText(f"{meta['total_bytes'] / (1024**2):.1f} MB")
            when = datetime.fromtimestamp(meta["last_indexed_at"]).strftime("%Y-%m-%d %H:%M")
            self.stat_last_indexed.setText(when)
        else:
            self.stat_files.setText("Not indexed yet")
            self.stat_size.setText("—")
            self.stat_last_indexed.setText("—")
