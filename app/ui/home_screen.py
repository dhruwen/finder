"""The single main page: folder picker + search + results + restructuring.

Everything a non-technical user needs day-to-day lives here, visible on the
page itself: pick a folder, search it, restructure/rename it. Only what
genuinely doesn't belong on this page — rebuilding the index, mismatch
warnings, and preferences — lives behind the Settings button, so it's out of
the way without hiding anything that people reach for often.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QComboBox, QToolButton, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu,
    QFileDialog, QMessageBox, QProgressBar, QFrame,
)

from app.core.search import SearchFilters, search, list_distinct_years, list_distinct_extensions
from app.core.metadata_extractor import month_label, extension_category, CATEGORY_ORDER
from app.core.size_estimate import estimate, format_confirmation_message
from app.ui.app_state import AppState
from app.ui.icons import category_icon
from app.ui.workers import IndexWorker
from app.ui.restructure_wizard import RestructureWizard
from app.ui import os_utils

COLUMNS = ["File name", "Path", "Detected name", "Doc type", "Year", "Month", "Extension", "Modified"]


class HomeScreen(QWidget):
    settingsRequested = pyqtSignal()
    moreFiltersVisibilityChanged = pyqtSignal(bool)

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._worker: IndexWorker | None = None
        self.state.indexChanged.connect(self._on_index_changed)
        self.state.rootChanged.connect(self._on_index_changed)
        self.state.auto_rename.renamed.connect(self._on_auto_renamed)
        self.state.auto_rename.failed.connect(self.status_label_set)
        self._build_ui()
        self._on_index_changed()

    # -- UI construction ----------------------------------------------------
    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 12, 16, 12)
        root_layout.setSpacing(10)

        root_layout.addLayout(self._build_top_bar())

        self.empty_state = self._build_empty_state()
        root_layout.addWidget(self.empty_state)

        self.search_area = QWidget()
        search_layout = QVBoxLayout(self.search_area)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)
        search_layout.addLayout(self._build_search_row())
        search_layout.addLayout(self._build_basic_filters_row())
        search_layout.addWidget(self._build_more_filters_panel())
        search_layout.addWidget(self._build_results_table(), 1)
        root_layout.addWidget(self.search_area, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root_layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusBar")
        root_layout.addWidget(self.status_label)

    def _build_top_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self.folder_label = QLabel("No folder selected")
        self.folder_label.setStyleSheet("font-weight: 600;")
        self.change_folder_btn = QPushButton("Choose folder…")
        self.change_folder_btn.clicked.connect(self.choose_folder)

        self.restructure_btn = QPushButton("Restructure && Rename…")
        self.restructure_btn.setEnabled(False)
        self.restructure_btn.setToolTip("Choose and index a folder first.")
        self.restructure_btn.clicked.connect(self.open_restructure_wizard)

        settings_btn = QPushButton("⚙  Settings")
        settings_btn.clicked.connect(self.settingsRequested.emit)

        bar.addWidget(QLabel("📁"))
        bar.addWidget(self.folder_label, 1)
        bar.addWidget(self.change_folder_btn)
        bar.addWidget(self.restructure_btn)
        bar.addSpacing(12)
        bar.addWidget(settings_btn)
        return bar

    def _build_empty_state(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("emptyState")
        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        title = QLabel("Welcome to Finder")
        title.setObjectName("screenTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Choose a folder and Finder will index it so you can search it instantly.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        start_btn = QPushButton("Choose folder to search")
        start_btn.setObjectName("primaryButton")
        start_btn.clicked.connect(self.choose_folder)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(start_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        return frame

    def _build_search_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by file name, client, or keyword…")
        self.search_box.returnPressed.connect(self.run_search)
        search_btn = QPushButton("Search")
        search_btn.setObjectName("primaryButton")
        search_btn.setDefault(True)
        search_btn.clicked.connect(self.run_search)
        row.addWidget(self.search_box, 1)
        row.addWidget(search_btn)
        return row

    def _build_basic_filters_row(self) -> QHBoxLayout:
        # No separate name field: the search box already matches the
        # "Detected name" column (it's part of the FTS index), so a second
        # box that only searched that one column just looked broken when a
        # word lived in the file name instead (e.g. "Challan").
        row = QHBoxLayout()
        row.addWidget(QLabel("Year:"))
        self.year_combo = QComboBox()
        self.year_combo.addItem("Any")
        row.addWidget(self.year_combo)

        row.addStretch(1)
        self.more_filters_btn = QPushButton("More filters  ▾")
        self.more_filters_btn.clicked.connect(self.toggle_more_filters)
        row.addWidget(self.more_filters_btn)
        return row

    def _build_more_filters_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("moreFilters")
        panel.setVisible(False)
        self.more_filters_panel = panel
        layout = QHBoxLayout(panel)

        layout.addWidget(QLabel("File type:"))
        # One dropdown button per category (Documents, Code, Images, ...),
        # each opening a checkable menu of just that category's extensions.
        # Populated in _populate_category_filters — only categories that
        # actually have files in the current index get a button at all.
        self.category_row = QHBoxLayout()
        self.category_row.setSpacing(6)
        layout.addLayout(self.category_row, 1)
        self.category_buttons: dict[str, QToolButton] = {}
        self.category_actions: dict[str, dict[str, QAction]] = {}

        reset_btn = QPushButton("Reset filters")
        reset_btn.clicked.connect(self.reset_filters)
        layout.addWidget(reset_btn)

        return panel

    def _build_results_table(self) -> QTableWidget:
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 220)
        self.table.doubleClicked.connect(self._open_selected_file)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        return self.table

    # -- folder selection / indexing -----------------------------------------
    def toggle_more_filters(self) -> None:
        self.set_more_filters_visible(not self.more_filters_panel.isVisible())

    def set_more_filters_visible(self, visible: bool) -> None:
        """Single source of truth for the More Filters panel — driven by
        either the in-page button or the menu bar's checkable View action,
        which stay in sync via `moreFiltersVisibilityChanged`."""
        self.more_filters_panel.setVisible(visible)
        self.more_filters_btn.setText("Fewer filters  ▴" if visible else "More filters  ▾")
        self.moreFiltersVisibilityChanged.emit(visible)

    def choose_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose folder to search")
        if not directory:
            return

        est = estimate(Path(directory))
        if est.file_count > 2000 or est.total_bytes > 500 * 1024 * 1024:
            reply = QMessageBox.question(
                self, "Confirm indexing", format_confirmation_message(est),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.state.set_root(directory)
        self._start_indexing()

    def _start_indexing(self) -> None:
        self.change_folder_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText("Indexing… this only reads file names and dates, never file contents.")
        db_path = self.state.settings.index_path_for(self.state.current_root)
        self._worker = IndexWorker(self.state.current_root, db_path)
        self._worker.finished_ok.connect(self._on_index_finished)
        self._worker.failed.connect(self._on_index_failed)
        self._worker.start()

    def _on_index_finished(self, stats) -> None:
        self.progress.setVisible(False)
        self.change_folder_btn.setEnabled(True)
        self.state.set_root(self.state.current_root)  # reopen conn with fresh data
        self.state.notify_index_changed()
        extra = f", {stats.mismatches} possibly misplaced" if stats.mismatches else ""
        self.status_label.setText(f"Indexed {stats.files_indexed} files in {stats.elapsed_seconds:.1f}s{extra}.")

    def _on_index_failed(self, error: str) -> None:
        self.progress.setVisible(False)
        self.change_folder_btn.setEnabled(True)
        QMessageBox.critical(self, "Indexing failed", error)

    def rebuild_current_index(self) -> None:
        """Re-scan the currently selected folder (menu bar: File > Rebuild Index)."""
        if not self.state.current_root:
            QMessageBox.information(self, "No folder selected", "Choose a folder to search first.")
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
        self._start_indexing()

    def open_restructure_wizard(self) -> None:
        """Launches the Restructure & Rename wizard directly from the main
        page (the wizard itself still requires a full preview + explicit
        confirmation before touching any file — this button only opens it)."""
        if not self.state.current_root:
            QMessageBox.information(self, "No folder selected", "Choose a folder to search first.")
            return
        wizard = RestructureWizard(self.state, self)
        wizard.exec()
        self.state.notify_index_changed()

    # -- reacting to state changes --------------------------------------------
    def _on_index_changed(self) -> None:
        has_root = bool(self.state.current_root)
        from app.core import db as db_mod
        is_indexed = has_root and self.state.conn is not None and db_mod.get_index_meta(self.state.conn, self.state.current_root) is not None

        self.empty_state.setVisible(not is_indexed)
        self.search_area.setVisible(is_indexed)

        self.restructure_btn.setEnabled(is_indexed)
        self.restructure_btn.setToolTip("" if is_indexed else "Choose and index a folder first.")

        if has_root:
            self.folder_label.setText(self.state.current_root)
            self.change_folder_btn.setText("Change folder…")
        else:
            self.folder_label.setText("No folder selected")
            self.change_folder_btn.setText("Choose folder…")

        if not is_indexed:
            return

        conn = self.state.conn
        self.year_combo.blockSignals(True)
        current_year = self.year_combo.currentText()
        self.year_combo.clear()
        self.year_combo.addItem("Any")
        for y in list_distinct_years(conn, self.state.current_root):
            self.year_combo.addItem(str(y))
        idx = self.year_combo.findText(current_year)
        self.year_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.year_combo.blockSignals(False)

        checked_before = set(self._checked_extensions())
        self._populate_category_filters(conn, checked_before)

        self.run_search()

    def _populate_category_filters(self, conn, checked_before: set[str]) -> None:
        """One dropdown button per category actually present in this index
        (Documents, Code, Images, ...) — categories with nothing in the
        current folder don't get a button at all, so the row only ever
        shows what's relevant here."""
        by_category: dict[str, list[str]] = {}
        for ext in list_distinct_extensions(conn, self.state.current_root):
            by_category.setdefault(extension_category(ext), []).append(ext)

        while self.category_row.count():
            item = self.category_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.category_buttons.clear()
        self.category_actions.clear()

        for category in CATEGORY_ORDER:
            exts = by_category.get(category)
            if not exts:
                continue

            btn = QToolButton()
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(btn)
            actions: dict[str, QAction] = {}
            for ext in sorted(exts):
                action = QAction(ext, menu)
                action.setCheckable(True)
                action.setChecked(ext in checked_before)
                action.toggled.connect(lambda _checked, cat=category: self._on_category_filter_changed(cat))
                menu.addAction(action)
                actions[ext] = action
            btn.setMenu(menu)
            self.category_row.addWidget(btn)
            self.category_buttons[category] = btn
            self.category_actions[category] = actions
            self._refresh_category_button_label(category)

        self.category_row.addStretch(1)

    def _refresh_category_button_label(self, category: str) -> None:
        btn = self.category_buttons.get(category)
        actions = self.category_actions.get(category)
        if not btn or not actions:
            return
        checked = sum(1 for a in actions.values() if a.isChecked())
        icon = category_icon(category)
        label = f"{icon} {category} ({checked}) ▾" if checked else f"{icon} {category} ▾"
        btn.setText(label)

    def _on_category_filter_changed(self, category: str) -> None:
        self._refresh_category_button_label(category)
        self.run_search()

    def _checked_extensions(self) -> list[str]:
        result = []
        for actions in self.category_actions.values():
            result.extend(ext for ext, action in actions.items() if action.isChecked())
        return result

    def reset_filters(self) -> None:
        self.search_box.clear()
        self.year_combo.setCurrentIndex(0)
        for category, actions in self.category_actions.items():
            for action in actions.values():
                action.blockSignals(True)
                action.setChecked(False)
                action.blockSignals(False)
            self._refresh_category_button_label(category)
        self.run_search()

    def _collect_filters(self) -> SearchFilters:
        year = None
        if self.year_combo.currentText() != "Any":
            year = int(self.year_combo.currentText())

        return SearchFilters(
            text=self.search_box.text(),
            year=year,
            extensions=self._checked_extensions(),
            root=self.state.current_root,
        )

    def run_search(self) -> None:
        conn = self.state.conn
        if not conn:
            return

        filters = self._collect_filters()
        start = time.perf_counter()
        rows = search(conn, filters, limit=2000)
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            modified = datetime.fromtimestamp(row["modified_at"]).strftime("%Y-%m-%d %H:%M") if row["modified_at"] else ""
            values = [
                row["name"], row["path"], row["client_name"] or "", row["doc_type"] or "",
                str(row["year"] or ""), month_label(row["month"]), row["extension"] or "", modified,
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["path"])
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)

        capped = " (showing first 2000)" if len(rows) == 2000 else ""
        self.status_label.setText(f"Found {len(rows)} file(s) in {elapsed_ms:.1f} ms{capped}")

    def status_label_set(self, text: str) -> None:
        self.status_label.setText(text)

    def _on_auto_renamed(self, event) -> None:
        self.status_label.setText(
            f"Auto-renamed: {Path(event.old_path).name} → {Path(event.new_path).name}  "
            "(undo in Settings → Auto-rename)"
        )

    # -- result actions -------------------------------------------------------
    def _selected_path(self) -> str | None:
        items = self.table.selectedItems()
        if not items:
            return None
        row = items[0].row()
        cell = self.table.item(row, 0)
        return cell.data(Qt.ItemDataRole.UserRole) if cell else None

    def copy_selected_path_to_clipboard(self) -> None:
        path = self._selected_path()
        if not path:
            self.status_label.setText("Select a result first to copy its path.")
            return
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(path)
        self.status_label.setText(f"Copied path to clipboard: {path}")

    def _open_selected_file(self) -> None:
        path = self._selected_path()
        if not path:
            return
        action = self.state.settings.default_file_action
        if action == "open_file":
            os_utils.open_file(path)
        elif action == "open_location":
            os_utils.reveal_in_file_manager(path)
        else:
            self._prompt_open_action(path)

    def _prompt_open_action(self, path: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Open item")
        box.setText(f"What would you like to do with:\n\n{Path(path).name}")
        open_btn = box.addButton("Open File", QMessageBox.ButtonRole.AcceptRole)
        reveal_btn = box.addButton("Open File Location", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        remember_check = QCheckBox("Always do this — don't ask again (change anytime in Settings)")
        box.setCheckBox(remember_check)
        box.exec()

        clicked = box.clickedButton()
        if clicked == open_btn:
            os_utils.open_file(path)
            if remember_check.isChecked():
                self.state.settings.default_file_action = "open_file"
                self.state.settings.save()
        elif clicked == reveal_btn:
            os_utils.reveal_in_file_manager(path)
            if remember_check.isChecked():
                self.state.settings.default_file_action = "open_location"
                self.state.settings.save()

    def _show_context_menu(self, pos) -> None:
        path = self._selected_path()
        if not path:
            return
        menu = QMenu(self)
        open_action = menu.addAction("Open file")
        reveal_action = menu.addAction("Open containing folder")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == open_action:
            os_utils.open_file(path)
        elif action == reveal_action:
            os_utils.reveal_in_file_manager(path)
