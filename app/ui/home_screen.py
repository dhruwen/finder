"""The single main page: folder picker + search + results.

Everything a non-technical user needs day-to-day lives here: pick a folder
once, then search it. Everything else (rebuilding the index, restructuring,
warnings, preferences) lives behind the Settings button in the top bar, kept
out of the way until someone actually wants it.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QComboBox, QListWidget, QListWidgetItem, QDateEdit, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu,
    QFileDialog, QMessageBox, QProgressBar, QFrame,
)

from app.core.search import (
    SearchFilters, resolve_quick_range, search, list_distinct_doc_types, list_distinct_years,
)
from app.core.size_estimate import estimate, format_confirmation_message
from app.ui.app_state import AppState
from app.ui.workers import IndexWorker
from app.ui import os_utils

COMMON_EXTENSIONS = ["pdf", "xlsx", "xls", "docx", "doc", "csv", "txt", "ppt", "pptx", "jpg", "png", "zip"]
MONTHS = ["Any", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
COLUMNS = ["File name", "Path", "Client", "Doc type", "Year", "Month", "Extension", "Modified"]


class HomeScreen(QWidget):
    settingsRequested = pyqtSignal()

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._worker: IndexWorker | None = None
        self.state.indexChanged.connect(self._on_index_changed)
        self.state.rootChanged.connect(self._on_index_changed)
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
        settings_btn = QPushButton("⚙  Settings")
        settings_btn.clicked.connect(self.settingsRequested.emit)

        bar.addWidget(QLabel("📁"))
        bar.addWidget(self.folder_label, 1)
        bar.addWidget(self.change_folder_btn)
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
        row = QHBoxLayout()
        row.addWidget(QLabel("Client:"))
        self.client_edit = QLineEdit()
        self.client_edit.setPlaceholderText("e.g. John")
        self.client_edit.setMaximumWidth(180)
        row.addWidget(self.client_edit)

        row.addWidget(QLabel("Document type:"))
        self.doctype_combo = QComboBox()
        self.doctype_combo.addItem("Any")
        self.doctype_combo.setMinimumWidth(140)
        row.addWidget(self.doctype_combo)

        row.addWidget(QLabel("Year:"))
        self.year_combo = QComboBox()
        self.year_combo.addItem("Any")
        row.addWidget(self.year_combo)

        row.addStretch(1)
        self.more_filters_btn = QPushButton("More filters  ▾")
        self.more_filters_btn.clicked.connect(self._toggle_more_filters)
        row.addWidget(self.more_filters_btn)
        return row

    def _build_more_filters_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("moreFilters")
        panel.setVisible(False)
        self.more_filters_panel = panel
        layout = QVBoxLayout(panel)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Month:"))
        self.month_combo = QComboBox()
        self.month_combo.addItems(MONTHS)
        row1.addWidget(self.month_combo)

        row1.addWidget(QLabel("From:"))
        self.date_from = QDateEdit(calendarPopup=True)
        self.date_from.setDate(QDate.currentDate().addYears(-1))
        row1.addWidget(self.date_from)
        row1.addWidget(QLabel("To:"))
        self.date_to = QDateEdit(calendarPopup=True)
        self.date_to.setDate(QDate.currentDate())
        row1.addWidget(self.date_to)
        self.use_date_range = QCheckBox("Use date range")
        row1.addWidget(self.use_date_range)
        for label, key in [("This month", "this_month"), ("Past 3 mo", "past_3_months"),
                            ("This year", "this_year"), ("Past 1 yr", "past_1_year")]:
            btn = QPushButton(label)
            btn.setProperty("quickRangeKey", key)
            btn.clicked.connect(self._apply_quick_range)
            row1.addWidget(btn)
        row1.addStretch(1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("File type:"))
        self.extension_list = QListWidget()
        self.extension_list.setFlow(QListWidget.Flow.LeftToRight)
        self.extension_list.setWrapping(True)
        self.extension_list.setFixedHeight(56)
        for ext in COMMON_EXTENSIONS:
            item = QListWidgetItem(ext)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.extension_list.addItem(item)
        row2.addWidget(self.extension_list, 1)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Folder contains:"))
        self.path_pattern_edit = QLineEdit()
        self.path_pattern_edit.setPlaceholderText("e.g. Received/2024/*")
        row3.addWidget(self.path_pattern_edit)
        self.mismatch_only_check = QCheckBox("Only possibly-misplaced files")
        row3.addWidget(self.mismatch_only_check)
        reset_btn = QPushButton("Reset filters")
        reset_btn.clicked.connect(self.reset_filters)
        row3.addWidget(reset_btn)
        layout.addLayout(row3)

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
    def _toggle_more_filters(self) -> None:
        showing = not self.more_filters_panel.isVisible()
        self.more_filters_panel.setVisible(showing)
        self.more_filters_btn.setText("Fewer filters  ▴" if showing else "More filters  ▾")

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

    # -- reacting to state changes --------------------------------------------
    def _on_index_changed(self) -> None:
        has_root = bool(self.state.current_root)
        from app.core import db as db_mod
        is_indexed = has_root and self.state.conn is not None and db_mod.get_index_meta(self.state.conn, self.state.current_root) is not None

        self.empty_state.setVisible(not is_indexed)
        self.search_area.setVisible(is_indexed)

        if has_root:
            self.folder_label.setText(self.state.current_root)
            self.change_folder_btn.setText("Change folder…")
        else:
            self.folder_label.setText("No folder selected")
            self.change_folder_btn.setText("Choose folder…")

        if not is_indexed:
            return

        conn = self.state.conn
        self.doctype_combo.blockSignals(True)
        current_dt = self.doctype_combo.currentText()
        self.doctype_combo.clear()
        self.doctype_combo.addItem("Any")
        for dt in list_distinct_doc_types(conn, self.state.current_root):
            self.doctype_combo.addItem(dt)
        idx = self.doctype_combo.findText(current_dt)
        self.doctype_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.doctype_combo.blockSignals(False)

        self.year_combo.blockSignals(True)
        current_year = self.year_combo.currentText()
        self.year_combo.clear()
        self.year_combo.addItem("Any")
        for y in list_distinct_years(conn, self.state.current_root):
            self.year_combo.addItem(str(y))
        idx = self.year_combo.findText(current_year)
        self.year_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.year_combo.blockSignals(False)

        self.run_search()

    def _apply_quick_range(self) -> None:
        btn = self.sender()
        key = btn.property("quickRangeKey")
        start_ts, end_ts = resolve_quick_range(key)
        self.use_date_range.setChecked(True)
        self.date_from.setDate(QDate.fromString(datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d"), "yyyy-MM-dd"))
        self.date_to.setDate(QDate.fromString(datetime.fromtimestamp(end_ts).strftime("%Y-%m-%d"), "yyyy-MM-dd"))
        self.run_search()

    def _checked_extensions(self) -> list[str]:
        result = []
        for i in range(self.extension_list.count()):
            item = self.extension_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.text())
        return result

    def reset_filters(self) -> None:
        self.search_box.clear()
        self.client_edit.clear()
        self.doctype_combo.setCurrentIndex(0)
        self.year_combo.setCurrentIndex(0)
        self.month_combo.setCurrentIndex(0)
        self.use_date_range.setChecked(False)
        for i in range(self.extension_list.count()):
            self.extension_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.path_pattern_edit.clear()
        self.mismatch_only_check.setChecked(False)
        self.run_search()

    def _collect_filters(self) -> SearchFilters:
        year = None
        if self.year_combo.currentText() != "Any":
            year = int(self.year_combo.currentText())
        month = None
        if self.month_combo.currentText() != "Any":
            month = MONTHS.index(self.month_combo.currentText())
        doc_types = []
        if self.doctype_combo.currentText() != "Any":
            doc_types = [self.doctype_combo.currentText()]

        date_from = date_to = None
        if self.use_date_range.isChecked():
            date_from = datetime(self.date_from.date().year(), self.date_from.date().month(), self.date_from.date().day()).timestamp()
            dt = self.date_to.date()
            date_to = datetime(dt.year(), dt.month(), dt.day(), 23, 59, 59).timestamp()

        return SearchFilters(
            text=self.search_box.text(),
            client_name=self.client_edit.text(),
            doc_types=doc_types,
            year=year,
            month=month,
            date_from=date_from,
            date_to=date_to,
            extensions=self._checked_extensions(),
            path_pattern=self.path_pattern_edit.text(),
            only_mismatches=self.mismatch_only_check.isChecked(),
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
                str(row["year"] or ""), str(row["month"] or ""), row["extension"] or "", modified,
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(val)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["path"])
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)

        capped = " (showing first 2000)" if len(rows) == 2000 else ""
        self.status_label.setText(f"Found {len(rows)} file(s) in {elapsed_ms:.1f} ms{capped}")

    # -- result actions -------------------------------------------------------
    def _selected_path(self) -> str | None:
        items = self.table.selectedItems()
        if not items:
            return None
        row = items[0].row()
        cell = self.table.item(row, 0)
        return cell.data(Qt.ItemDataRole.UserRole) if cell else None

    def _open_selected_file(self) -> None:
        path = self._selected_path()
        if path:
            os_utils.open_file(path)

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
