"""Warnings / Suggestions screen: lists files whose folder and file-name
metadata disagree ("possibly misplaced"). Informational only in Phase-1."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,
)

from app.ui.app_state import AppState
from app.ui import os_utils

COLUMNS = ["File path", "Reason"]


class WarningsScreen(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.state.indexChanged.connect(self.refresh)
        self.state.rootChanged.connect(self.refresh)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Warnings & Suggestions")
        title.setObjectName("screenTitle")
        layout.addWidget(title)

        self.subtitle = QLabel(
            "Files where the folder location and the file name suggest different "
            "clients, document types, or years. Review only — nothing is changed automatically."
        )
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 380)
        self.table.doubleClicked.connect(self._open_containing_folder)
        layout.addWidget(self.table)

        self.count_label = QLabel("")
        layout.addWidget(self.count_label)

    def refresh(self) -> None:
        conn = self.state.conn
        self.table.setRowCount(0)
        if not conn:
            self.count_label.setText("No folder indexed yet.")
            return
        rows = conn.execute(
            "SELECT path, mismatch_reason FROM files WHERE mismatch_flag = 1 AND root = ? ORDER BY path",
            (self.state.current_root,),
        ).fetchall()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            path_item = QTableWidgetItem(row["path"])
            reason_item = QTableWidgetItem(row["mismatch_reason"] or "")
            self.table.setItem(r, 0, path_item)
            self.table.setItem(r, 1, reason_item)
        self.count_label.setText(f"{len(rows)} possibly-misplaced file(s) found.")

    def _open_containing_folder(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        path = self.table.item(items[0].row(), 0).text()
        os_utils.reveal_in_file_manager(path)
