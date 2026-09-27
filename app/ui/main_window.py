"""Main application window: one search page with everything primary visible
directly on it (choose folder, search, restructure & rename), plus a ⚙
Settings button for the occasional stuff (index management, warnings,
preferences). The menu bar deliberately does NOT repeat those on-page
actions — it only holds things that have no on-page button at all (Open
Recent, Copy File Path, Refresh Search, ...) or that are pure OS/window
chrome (Quit, About). Anything that already has a single, always-visible
on-page button lives there and nowhere else, so there's exactly one way to
do each thing.

The menu bar is built with QMainWindow.menuBar() — Qt places it natively per
platform with no extra code: inside the window at the top on Windows/Linux
(like VS Code), and in the OS-level menu bar at the top of the screen on
macOS. Quit/About additionally carry an explicit `setMenuRole` so Qt
relocates them into the native macOS Application menu instead of leaving
them under File/Help, matching real macOS conventions.
"""
from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMainWindow, QMessageBox

from app import __version__
from app.ui.app_state import AppState
from app.ui.home_screen import HomeScreen
from app.ui.resources import resource_path
from app.ui.settings_dialog import SettingsDialog
from app.ui.settings_screen import ABOUT_TEXT
from app.ui import os_utils

RECENT_FOLDERS_LIMIT = 10


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.state = AppState()
        self.setWindowTitle(f"Finder — File Search & Restructuring Tool v{__version__}")
        self.resize(1100, 720)

        self.home = HomeScreen(self.state)
        self.home.settingsRequested.connect(self.open_settings)
        self.setCentralWidget(self.home)

        self._build_menu_bar()
        self.statusBar().hide()

    # -- menu construction ----------------------------------------------------
    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        self._build_file_menu(menu_bar)
        self._build_edit_menu(menu_bar)
        self._build_view_menu(menu_bar)
        self._build_help_menu(menu_bar)

    def _build_file_menu(self, menu_bar) -> None:
        file_menu = menu_bar.addMenu("&File")

        # No "Choose Folder" here on purpose — the page's own button does
        # that, and its label ("Choose folder…" / "Change folder…") already
        # reflects the current state better than a static menu item could.
        self.recent_menu = file_menu.addMenu("Open Recent")
        self.recent_menu.aboutToShow.connect(self._refresh_recent_menu)

        rebuild_action = QAction("Rebuild Index", self, shortcut="Ctrl+R")
        rebuild_action.triggered.connect(self.home.rebuild_current_index)
        file_menu.addAction(rebuild_action)

        file_menu.addSeparator()
        quit_action = QAction("Quit", self, shortcut=QKeySequence.StandardKey.Quit)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _build_edit_menu(self, menu_bar) -> None:
        edit_menu = menu_bar.addMenu("&Edit")

        find_action = QAction("Find", self, shortcut=QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self._focus_search)
        edit_menu.addAction(find_action)

        copy_path_action = QAction("Copy File Path", self, shortcut="Ctrl+Shift+C")
        copy_path_action.triggered.connect(self.home.copy_selected_path_to_clipboard)
        edit_menu.addAction(copy_path_action)

        edit_menu.addSeparator()
        reset_action = QAction("Reset Filters", self, shortcut="Ctrl+Shift+R")
        reset_action.triggered.connect(self.home.reset_filters)
        edit_menu.addAction(reset_action)

    def _build_view_menu(self, menu_bar) -> None:
        view_menu = menu_bar.addMenu("&View")

        refresh_action = QAction("Refresh Search", self, shortcut=QKeySequence.StandardKey.Refresh)
        refresh_action.triggered.connect(self.home.run_search)
        view_menu.addAction(refresh_action)

        # Checkable and kept in sync with the page's own "More filters"
        # button in both directions (see HomeScreen.set_more_filters_visible)
        # — this one stays here too since it's a fast, keyboard-driven
        # toggle rather than a whole separate screen/dialog.
        self.toggle_filters_action = QAction("More Filters", self, shortcut="Ctrl+Shift+F")
        self.toggle_filters_action.setCheckable(True)
        self.toggle_filters_action.toggled.connect(self.home.set_more_filters_visible)
        self.home.moreFiltersVisibilityChanged.connect(self.toggle_filters_action.setChecked)
        view_menu.addAction(self.toggle_filters_action)

    def _build_help_menu(self, menu_bar) -> None:
        help_menu = menu_bar.addMenu("&Help")

        guide_action = QAction("User Guide", self)
        guide_action.triggered.connect(self._open_user_guide)
        help_menu.addAction(guide_action)

        about_action = QAction("About Finder", self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # -- action handlers --------------------------------------------------------
    def _focus_search(self) -> None:
        self.home.search_box.setFocus()
        self.home.search_box.selectAll()

    def _open_user_guide(self) -> None:
        guide = resource_path("docs", "USER_GUIDE.md")
        if guide.exists():
            os_utils.open_file(str(guide))
        else:
            QMessageBox.information(self, "User Guide", "The user guide file could not be found.")

    def _show_about(self) -> None:
        QMessageBox.about(self, "About Finder", ABOUT_TEXT)

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        # Most-recently-used first; current root excluded since re-opening
        # what's already open isn't a meaningful "recent" action.
        recents = [r for r in reversed(self.state.settings.roots) if r != self.state.current_root]
        recents = recents[:RECENT_FOLDERS_LIMIT]

        if not recents:
            empty_action = QAction("No other recent folders", self)
            empty_action.setEnabled(False)
            self.recent_menu.addAction(empty_action)
            return

        for root in recents:
            action = QAction(root, self)
            action.triggered.connect(lambda checked=False, r=root: self.state.set_root(r))
            self.recent_menu.addAction(action)

        self.recent_menu.addSeparator()
        clear_action = QAction("Clear Recent Folders", self)
        clear_action.triggered.connect(self._clear_recent_folders)
        self.recent_menu.addAction(clear_action)

    def _clear_recent_folders(self) -> None:
        current = self.state.current_root
        self.state.settings.roots = [current] if current else []
        self.state.settings.save()

    def open_settings(self, section: str | None = None) -> None:
        dialog = SettingsDialog(self.state, self)
        if section:
            dialog.open_at(section)
        dialog.exec()
        # Reindexing/preferences may have changed inside the dialog; make
        # sure the home page reflects the latest state.
        self.state.notify_index_changed()

    def closeEvent(self, event) -> None:
        self.state.close()
        super().closeEvent(event)
