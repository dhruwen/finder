"""Settings dialog: everything that isn't day-to-day searching lives here —
index management, restructuring, warnings, and preferences — behind a single
gear button so the main page stays uncluttered for non-technical users.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget,
    QPushButton, QWidget, QLabel,
)

from app.ui.app_state import AppState
from app.ui.index_screen import IndexScreen
from app.ui.warnings_screen import WarningsScreen
from app.ui.settings_screen import SettingsScreen
from app.ui.restructure_wizard import RestructureWizard

NAV_ITEMS = ["Index Management", "Restructure & Rename", "Warnings", "Preferences"]


class RestructurePage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Restructure & Rename Files")
        title.setObjectName("screenTitle")
        layout.addWidget(title)

        desc = QLabel(
            "For folders with inconsistent structure and naming, this wizard proposes a "
            "standard layout (Received/Year/Month/Client/DocType) and file names, shows a "
            "full preview of every change, and asks for explicit confirmation before touching "
            "any file. Nothing is changed until you approve the preview."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        start_btn = QPushButton("Start Restructure Wizard")
        start_btn.setObjectName("primaryButton")
        start_btn.clicked.connect(self._start_wizard)
        layout.addWidget(start_btn)
        layout.addStretch(1)

    def _start_wizard(self) -> None:
        wizard = RestructureWizard(self.state, self)
        wizard.exec()


class SettingsDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Settings")
        self.resize(980, 660)

        outer = QVBoxLayout(self)
        body = QHBoxLayout()

        self.nav = QListWidget()
        self.nav.setFixedWidth(190)
        self.nav.addItems(NAV_ITEMS)
        self.nav.currentRowChanged.connect(self._on_nav_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(IndexScreen(state))
        self.stack.addWidget(RestructurePage(state))
        self.stack.addWidget(WarningsScreen(state))
        self.stack.addWidget(SettingsScreen(state))

        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        outer.addLayout(button_row)

        self.nav.setCurrentRow(0)

    def _on_nav_changed(self, row: int) -> None:
        self.stack.setCurrentIndex(row)

    def open_at(self, section: str) -> None:
        if section in NAV_ITEMS:
            self.nav.setCurrentRow(NAV_ITEMS.index(section))
