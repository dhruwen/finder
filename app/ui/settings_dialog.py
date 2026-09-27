"""Settings dialog: everything that isn't day-to-day searching or
restructuring lives here — index management, warnings, and preferences —
behind a single gear button so the main page stays uncluttered for
non-technical users. Restructure & Rename lives as its own button directly
on the main page (home_screen.py) instead of in here, since it's a primary
feature, not a settings tweak — see HomeScreen.open_restructure_wizard.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget, QPushButton

from app.ui.app_state import AppState
from app.ui.index_screen import IndexScreen
from app.ui.warnings_screen import WarningsScreen
from app.ui.settings_screen import SettingsScreen

NAV_ITEMS = ["Index Management", "Warnings", "Preferences"]


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
