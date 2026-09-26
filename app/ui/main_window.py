"""Main application window: one search page, with everything else tucked
behind the Settings button so the app stays simple for non-technical users."""
from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow

from app import __version__
from app.ui.app_state import AppState
from app.ui.home_screen import HomeScreen
from app.ui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.state = AppState()
        self.setWindowTitle(f"Finder — File Search & Restructuring Tool v{__version__}")
        self.resize(1100, 720)

        self.home = HomeScreen(self.state)
        self.home.settingsRequested.connect(self.open_settings)
        self.setCentralWidget(self.home)

        self.statusBar().hide()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.state, self)
        dialog.exec()
        # Reindexing/restructuring/preferences may have changed inside the
        # dialog; make sure the home page reflects the latest state.
        self.state.notify_index_changed()

    def closeEvent(self, event) -> None:
        self.state.close()
        super().closeEvent(event)
