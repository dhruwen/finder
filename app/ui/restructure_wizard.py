"""Restructure / Rename wizard (Type-3 users): select root -> choose mode ->
preview -> confirm -> apply with progress -> completion + report link.

Every step that can change files requires an explicit confirmation dialog,
per the safety requirements: nothing is moved/renamed without the user
reviewing a full old->new preview and clicking "Yes, apply changes".
"""
from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QProgressBar, QMessageBox, QFileDialog, QCheckBox,
    QTextEdit,
)

from app.core.migration import summarize, write_report
from app.ui.app_state import AppState
from app.ui.workers import RestructureApplyWorker, RestructurePlanWorker
from app.ui import os_utils

PAGE_ROOT, PAGE_MODE, PAGE_PREVIEW, PAGE_CONFIRM, PAGE_PROGRESS, PAGE_DONE = range(6)


class RootPage(QWizardPage):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setTitle("Step 1: Select root folder")
        layout = QVBoxLayout(self)
        self.label = QLabel()
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.change_btn = QPushButton("Choose a different folder…")
        self.change_btn.clicked.connect(self._choose)
        layout.addWidget(self.change_btn)
        layout.addStretch(1)

    def initializePage(self) -> None:
        self._refresh_label()

    def _refresh_label(self) -> None:
        if self.state.current_root:
            self.label.setText(
                f"Restructuring will run on the currently indexed root:\n\n{self.state.current_root}\n\n"
                "This folder must already be indexed (see Index Management)."
            )
        else:
            self.label.setText("No root is currently selected. Choose a folder to restructure.")

    def _choose(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select root folder")
        if directory:
            self.state.set_root(directory)
            self._refresh_label()

    def isComplete(self) -> bool:
        return bool(self.state.current_root and self.state.conn)


class ModePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Step 2: Choose restructure mode")
        layout = QVBoxLayout(self)
        self.group = QButtonGroup(self)
        self.full_radio = QRadioButton("Full restructure + rename (recommended for messy folders)")
        self.full_radio.setChecked(True)
        full_desc = QLabel("Moves files into: Received/<Year>/<Month>/<Client>/<DocType>/ and renames them.")
        full_desc.setWordWrap(True)
        full_desc.setStyleSheet("color: #666; margin-left: 22px;")
        self.rename_radio = QRadioButton("Rename only, keep current folder structure")
        rename_desc = QLabel("Files stay where they are; only the file name is standardized.")
        rename_desc.setWordWrap(True)
        rename_desc.setStyleSheet("color: #666; margin-left: 22px;")
        self.group.addButton(self.full_radio)
        self.group.addButton(self.rename_radio)
        layout.addWidget(self.full_radio)
        layout.addWidget(full_desc)
        layout.addWidget(self.rename_radio)
        layout.addWidget(rename_desc)
        layout.addStretch(1)

    def mode(self) -> str:
        return "full" if self.full_radio.isChecked() else "rename_only"


class PreviewPage(QWizardPage):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setTitle("Step 3: Preview changes")
        self.plan = None
        self._worker = None
        layout = QVBoxLayout(self)
        self.summary_label = QLabel("Computing preview…")
        layout.addWidget(self.summary_label)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Old path", "New path", "Note"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def initializePage(self) -> None:
        wizard = self.wizard()
        mode = wizard.mode_page.mode()
        self.summary_label.setText("Computing preview…")
        self.table.setRowCount(0)
        db_path = self.state.settings.index_path_for(self.state.current_root)
        self._worker = RestructurePlanWorker(self.state.current_root, db_path, mode)
        self._worker.finished_ok.connect(self._on_plan_ready)
        self._worker.failed.connect(self._on_plan_failed)
        self._worker.start()
        self.completeChanged.emit()

    def _on_plan_ready(self, plan) -> None:
        self.plan = plan
        self.wizard().plan = plan
        self.table.setRowCount(len(plan.changes))
        for r, change in enumerate(plan.changes):
            self.table.setItem(r, 0, QTableWidgetItem(change.old_path))
            self.table.setItem(r, 1, QTableWidgetItem(change.new_path))
            self.table.setItem(r, 2, QTableWidgetItem(change.conflict or ""))
        self.summary_label.setText(
            f"{plan.files_affected} file(s) will be moved/renamed. "
            f"{len(plan.new_folders)} new folder(s) will be created. "
            f"{plan.conflicts} naming conflict(s) auto-resolved. "
            f"{plan.skipped_unchanged} file(s) already match the convention and are skipped."
        )
        self.completeChanged.emit()

    def _on_plan_failed(self, error: str) -> None:
        self.summary_label.setText(f"Failed to compute preview: {error}")
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self.plan is not None and self.plan.files_affected > 0


class ConfirmPage(QWizardPage):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setTitle("Step 4: Confirm")
        layout = QVBoxLayout(self)
        self.text_label = QLabel()
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self.text_label)
        self.ack_check = QCheckBox("I understand and want to apply these changes")
        self.ack_check.stateChanged.connect(self.completeChanged)
        layout.addWidget(self.ack_check)
        layout.addStretch(1)

    def initializePage(self) -> None:
        plan = self.wizard().plan
        self.ack_check.setChecked(False)
        if plan is None:
            self.text_label.setText("No plan available.")
            return
        self.text_label.setText(
            f"This will move/rename {plan.files_affected} file(s) and create "
            f"{len(plan.new_folders)} new folder(s) inside:\n\n{self.state.current_root}\n\n"
            "All changes stay inside this folder. A migration report (old path -> new "
            "path, status) will be saved after the operation. This action can be "
            "partially reversed by moving files back manually using the report, "
            "but is not automatically undoable — review the preview carefully."
        )

    def isComplete(self) -> bool:
        return self.ack_check.isChecked()

    def validatePage(self) -> bool:
        reply = QMessageBox.question(
            self, "Confirm restructure",
            "This will move/rename files as previewed. Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes


class ProgressPage(QWizardPage):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setTitle("Applying changes…")
        self._done = False
        self._worker = None
        layout = QVBoxLayout(self)
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.current_label = QLabel("")
        layout.addWidget(self.current_label)
        self.error_box = QTextEdit()
        self.error_box.setReadOnly(True)
        self.error_box.setPlaceholderText("Errors, if any, will appear here.")
        layout.addWidget(self.error_box)

    def initializePage(self) -> None:
        self._done = False
        self.completeChanged.emit()
        plan = self.wizard().plan
        self.progress_bar.setRange(0, max(plan.files_affected, 1))
        self.progress_bar.setValue(0)
        db_path = self.state.settings.index_path_for(self.state.current_root)
        self._worker = RestructureApplyWorker(self.state.current_root, db_path, plan, dry_run=False)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, done: int, total: int, path: str) -> None:
        self.progress_bar.setValue(done)
        self.current_label.setText(f"{done}/{total}: {path}")

    def _on_finished(self, results) -> None:
        self._done = True
        self.wizard().results = results
        errors = [r for r in results if r.status == "error"]
        if errors:
            self.error_box.setPlainText("\n".join(f"{e.old_path}: {e.error}" for e in errors))
        self.current_label.setText("Done.")
        self.completeChanged.emit()
        self.wizard().next()

    def _on_failed(self, error: str) -> None:
        self._done = True
        self.error_box.setPlainText(f"Fatal error: {error}")
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._done

    def isCommitPage(self) -> bool:
        return True


class DonePage(QWizardPage):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setTitle("Restructure complete")
        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.report_btn = QPushButton("Open migration report")
        self.report_btn.clicked.connect(self._open_report)
        layout.addWidget(self.report_btn)
        layout.addStretch(1)
        self._report_path: Path | None = None

    def initializePage(self) -> None:
        results = self.wizard().results or []
        summary = summarize(results)
        reports_dir = Path(self.state.current_root) / ".finder_index" / "reports"
        report_path = reports_dir / f"migration_{int(time.time())}.csv"
        write_report(results, report_path, fmt="csv")
        self._report_path = report_path
        self.summary_label.setText(
            f"Success: {summary.get('success', 0)}\n"
            f"Errors: {summary.get('error', 0)}\n\n"
            f"Report saved to:\n{report_path}"
        )
        self.state.notify_index_changed()

    def _open_report(self) -> None:
        if self._report_path:
            os_utils.open_file(str(self._report_path))


class RestructureWizard(QWizard):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.plan = None
        self.results = None
        self.setWindowTitle("Restructure Files")
        self.setOption(QWizard.WizardOption.NoBackButtonOnLastPage, True)
        self.setMinimumSize(820, 560)

        self.root_page = RootPage(state)
        self.mode_page = ModePage()
        self.preview_page = PreviewPage(state)
        self.confirm_page = ConfirmPage(state)
        self.progress_page = ProgressPage(state)
        self.done_page = DonePage(state)

        self.setPage(PAGE_ROOT, self.root_page)
        self.setPage(PAGE_MODE, self.mode_page)
        self.setPage(PAGE_PREVIEW, self.preview_page)
        self.setPage(PAGE_CONFIRM, self.confirm_page)
        self.setPage(PAGE_PROGRESS, self.progress_page)
        self.setPage(PAGE_DONE, self.done_page)

    def reject(self) -> None:
        if self.currentId() == PAGE_PROGRESS and not self.progress_page.isComplete():
            QMessageBox.warning(self, "Please wait", "File operations are in progress and cannot be cancelled.")
            return
        super().reject()
