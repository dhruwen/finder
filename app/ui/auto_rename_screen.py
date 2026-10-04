"""Settings -> Auto-rename: which folders keep their naming convention
automatically, what that convention is, and recent renames (with Undo)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QInputDialog, QMessageBox, QCheckBox,
)

from app.core import auto_rename as ar
from app.ui.app_state import AppState
from app.ui import os_utils

HELP_TEXT = (
    "Pick a folder and Finder renames any new file added to it so it matches "
    "the naming the folder already uses — no rules to write. For example, if "
    "a folder's files look like <i>20240301_Ramesh_ITR_Notes.pdf</i>, a new "
    "<i>scan0001.pdf</i> dropped into <i>Ramesh/ITR/</i> becomes "
    "<i>20241002_Ramesh_ITR.pdf</i>. Files are only renamed, never "
    "moved, and every rename can be undone below. Works while Finder is open."
)


class AutoRenameScreen(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.service = state.auto_rename
        self._build_ui()
        self._refresh_rules()
        self._refresh_history()
        self.service.renamed.connect(lambda _e: self._refresh_history())

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Auto-rename")
        title.setObjectName("screenTitle")
        layout.addWidget(title)
        intro = QLabel(HELP_TEXT)
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #6b7280;")
        layout.addWidget(intro)

        folders_group = QGroupBox("Watched folders")
        folders_layout = QVBoxLayout(folders_group)
        self.rules_table = QTableWidget(0, 4)
        self.rules_table.setHorizontalHeaderLabels(["On", "Folder", "Naming", "Subfolders"])
        self.rules_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.rules_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.rules_table.verticalHeader().setVisible(False)
        self.rules_table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        header = self.rules_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.rules_table.itemSelectionChanged.connect(self._update_buttons)
        folders_layout.addWidget(self.rules_table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add folder…")
        add_btn.clicked.connect(self._add_folder)
        if self.state.current_root:
            add_current_btn = QPushButton("Add current folder")
            add_current_btn.setToolTip(self.state.current_root)
            add_current_btn.clicked.connect(lambda: self._add(self.state.current_root))
            btn_row.addWidget(add_current_btn)
        self.pattern_btn = QPushButton("Custom naming…")
        self.pattern_btn.setToolTip("Override the learned naming for the selected folder.")
        self.pattern_btn.clicked.connect(self._edit_pattern)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(add_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.pattern_btn)
        btn_row.addWidget(self.remove_btn)
        folders_layout.addLayout(btn_row)
        layout.addWidget(folders_group, 1)

        history_group = QGroupBox("Recent renames (this session)")
        history_layout = QVBoxLayout(history_group)
        self.history_table = QTableWidget(0, 3)
        self.history_table.setHorizontalHeaderLabels(["Time", "Original name", "Renamed to"])
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.verticalHeader().setVisible(False)
        h = self.history_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.history_table.itemSelectionChanged.connect(self._update_buttons)
        history_layout.addWidget(self.history_table)
        hist_btns = QHBoxLayout()
        log_btn = QPushButton("Open full log")
        log_btn.clicked.connect(self._open_log)
        self.undo_btn = QPushButton("Undo selected rename")
        self.undo_btn.clicked.connect(self._undo_selected)
        hist_btns.addWidget(log_btn)
        hist_btns.addStretch(1)
        hist_btns.addWidget(self.undo_btn)
        history_layout.addLayout(hist_btns)
        layout.addWidget(history_group, 1)

    # -- rules ----------------------------------------------------------------------
    def _refresh_rules(self) -> None:
        rules = self.state.settings.auto_rename_rules
        self.rules_table.setRowCount(len(rules))
        for r, rule in enumerate(rules):
            on = QCheckBox()
            on.setChecked(rule.get("enabled", True))
            on.toggled.connect(lambda checked, f=rule["folder"]: self._toggle(f, "enabled", checked))
            self.rules_table.setCellWidget(r, 0, self._centered(on))

            folder_item = QTableWidgetItem(rule["folder"])
            folder_item.setData(Qt.ItemDataRole.UserRole, rule["folder"])
            if not Path(rule["folder"]).is_dir():
                folder_item.setToolTip("This folder no longer exists.")
                folder_item.setForeground(Qt.GlobalColor.red)
            self.rules_table.setItem(r, 1, folder_item)

            pattern = rule.get("pattern") or ar.AUTO
            if pattern == ar.AUTO:
                naming = QTableWidgetItem("Learned from the folder's files")
                naming.setToolTip(self._learned_description(rule["folder"]))
            else:
                naming = QTableWidgetItem(pattern)
                naming.setToolTip("e.g. " + ar.example_for(ar.NamingPattern(pattern)))
            self.rules_table.setItem(r, 2, naming)

            subs = QCheckBox()
            subs.setChecked(rule.get("include_subfolders", True))
            subs.toggled.connect(lambda checked, f=rule["folder"]: self._toggle(f, "include_subfolders", checked))
            self.rules_table.setCellWidget(r, 3, self._centered(subs))
        self._update_buttons()

    @staticmethod
    def _centered(widget: QWidget) -> QWidget:
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(widget)
        return holder

    @staticmethod
    def _learned_description(folder: str) -> str:
        root = Path(folder)
        if not root.is_dir():
            return ""
        vocab = ar.build_folder_vocabulary(root, max_files=2000)
        learned = ar.learn_tree_pattern(root, vocab)
        if learned:
            return f"Detected naming: {learned.template}\ne.g. {ar.example_for(learned)}"
        return (
            "No consistent naming detected yet; Finder's standard naming is used:\n"
            f"{ar.DEFAULT_TEMPLATE}\nSubfolders with their own consistent naming keep theirs."
        )

    def _selected_folder(self) -> str | None:
        rows = self.rules_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.rules_table.item(rows[0].row(), 1)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _rule(self, folder: str) -> dict | None:
        return next((r for r in self.state.settings.auto_rename_rules if r["folder"] == folder), None)

    def _toggle(self, folder: str, key: str, value: bool) -> None:
        rule = self._rule(folder)
        if rule is None:
            return
        rule[key] = value
        self.state.settings.save()
        self.service.reload()

    def _add_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose a folder to keep tidy")
        if directory:
            self._add(directory)

    def _add(self, folder: str) -> None:
        folder = str(Path(folder).resolve())
        if self._rule(folder):
            QMessageBox.information(self, "Already added", f"{folder} is already in the list.")
            return
        self.service.set_rule(folder)
        self._refresh_rules()

    def _remove_selected(self) -> None:
        folder = self._selected_folder()
        if folder:
            self.service.remove_rule(folder)
            self._refresh_rules()

    def _edit_pattern(self) -> None:
        folder = self._selected_folder()
        rule = self._rule(folder) if folder else None
        if rule is None:
            return
        current = rule.get("pattern") or ar.AUTO
        tokens = "\n".join(f"  {{{t}}} — {desc}" for t, desc in ar.TOKEN_HELP.items())
        text, ok = QInputDialog.getText(
            self, "Custom naming",
            "Naming pattern for new files in this folder. Leave empty to go back to\n"
            "learning it from the folder's existing files.\n\n"
            f"Available slots (empty ones are dropped):\n{tokens}\n\n"
            f"Example: {ar.DEFAULT_TEMPLATE}",
            text="" if current == ar.AUTO else current,
        )
        if not ok:
            return
        text = text.strip()
        if text and not ar._TOKEN_RE.search(text):
            QMessageBox.warning(self, "Invalid pattern", "The pattern needs at least one slot, like {date} or {client}.")
            return
        self.service.set_rule(
            folder, enabled=rule.get("enabled", True), pattern=text or ar.AUTO,
            include_subfolders=rule.get("include_subfolders", True),
        )
        self._refresh_rules()

    # -- history --------------------------------------------------------------------
    def _refresh_history(self) -> None:
        events = list(reversed(self.service.history))
        self.history_table.setRowCount(len(events))
        for r, event in enumerate(events):
            when = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
            old = QTableWidgetItem(Path(event.old_path).name)
            old.setToolTip(event.old_path)
            new_name = Path(event.new_path).name + ("  (undone)" if event.undone else "")
            new = QTableWidgetItem(new_name)
            new.setToolTip(event.new_path)
            time_item = QTableWidgetItem(when)
            time_item.setData(Qt.ItemDataRole.UserRole, event)
            self.history_table.setItem(r, 0, time_item)
            self.history_table.setItem(r, 1, old)
            self.history_table.setItem(r, 2, new)
        self._update_buttons()

    def _undo_selected(self) -> None:
        rows = self.history_table.selectionModel().selectedRows()
        failed = 0
        for index in rows:
            event = self.history_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
            if not self.service.undo(event):
                failed += 1
        if failed:
            QMessageBox.warning(
                self, "Couldn't undo",
                f"{failed} rename(s) couldn't be undone — the file was moved, deleted, "
                "or a file with the original name already exists.",
            )
        self._refresh_history()

    def _open_log(self) -> None:
        path = self.service.log_path()
        if path.exists():
            os_utils.open_file(str(path))
        else:
            QMessageBox.information(self, "No log yet", "Nothing has been auto-renamed yet.")

    def _update_buttons(self) -> None:
        has_rule = self._selected_folder() is not None
        self.pattern_btn.setEnabled(has_rule)
        self.remove_btn.setEnabled(has_rule)
        rows = self.history_table.selectionModel().selectedRows()
        self.undo_btn.setEnabled(any(
            not self.history_table.item(i.row(), 0).data(Qt.ItemDataRole.UserRole).undone for i in rows
        ))
