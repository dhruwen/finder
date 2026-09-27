"""Settings / Preferences screen."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QCheckBox, QGroupBox, QFormLayout,
    QPushButton, QHBoxLayout, QFileDialog, QMessageBox, QTextBrowser, QComboBox,
)

from app import __version__
from app.core import ner
from app.ui.app_state import AppState

ABOUT_TEXT = f"""
<h3>Finder — File Search &amp; Restructuring Tool</h3>
<p>Version {__version__}</p>
<p>Local, offline file search and restructuring for CA/finance file archives.
File contents are never read or uploaded — only file names, paths, and
filesystem metadata (size, modified date) are indexed. Search and everyday
browsing use no AI at all.</p>
<p>The Restructure wizard optionally uses a small AI model to help spot
client/employee names in messy file names. It runs entirely on this
computer, is bundled with the app, and never sends anything over a network
connection. You can turn it off below.</p>
<p><b>Permissions:</b> the app only reads/writes the folder you explicitly
select as a root, plus its own settings and index files. It never accesses
any other location on disk. Use it on folders you own; if you see permission
errors, the affected files are skipped and logged rather than failing the
whole scan.</p>
"""


class SettingsScreen(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Settings")
        title.setObjectName("screenTitle")
        layout.addWidget(title)

        index_group = QGroupBox("Index storage")
        index_layout = QFormLayout(index_group)
        self.index_path_label = QLabel(self._current_index_path_text())
        self.index_path_label.setWordWrap(True)
        index_layout.addRow("Current index location:", self.index_path_label)
        choose_btn = QPushButton("Choose custom location for this root…")
        choose_btn.clicked.connect(self._choose_custom_index_location)
        index_layout.addRow(choose_btn)
        layout.addWidget(index_group)

        prefs_group = QGroupBox("Preferences")
        prefs_layout = QVBoxLayout(prefs_group)
        self.show_warnings_check = QCheckBox("Show mismatch warnings")
        self.show_warnings_check.setChecked(self.state.settings.show_mismatch_warnings)
        self.show_warnings_check.stateChanged.connect(self._save_prefs)
        self.ask_rebuild_check = QCheckBox("Ask before rebuilding index")
        self.ask_rebuild_check.setChecked(self.state.settings.ask_before_rebuild)
        self.ask_rebuild_check.stateChanged.connect(self._save_prefs)
        prefs_layout.addWidget(self.show_warnings_check)
        prefs_layout.addWidget(self.ask_rebuild_check)

        self.use_ai_check = QCheckBox("Use AI-assisted name suggestions during restructuring")
        self.use_ai_check.setChecked(self.state.settings.use_ai_suggestions)
        self.use_ai_check.stateChanged.connect(self._save_prefs)
        prefs_layout.addWidget(self.use_ai_check)
        ai_status = QLabel(
            "Runs fully offline, on this computer only."
            if ner.is_available()
            else "Not available on this installation — restructuring will use standard rules only."
        )
        ai_status.setStyleSheet("color: #6b7280; margin-left: 22px;")
        prefs_layout.addWidget(ai_status)

        file_action_row = QHBoxLayout()
        file_action_row.addWidget(QLabel("When you open a search result:"))
        self.file_action_combo = QComboBox()
        self.file_action_combo.addItem("Ask each time", "ask")
        self.file_action_combo.addItem("Always open the file", "open_file")
        self.file_action_combo.addItem("Always open its folder", "open_location")
        current_idx = self.file_action_combo.findData(self.state.settings.default_file_action)
        self.file_action_combo.setCurrentIndex(current_idx if current_idx >= 0 else 0)
        self.file_action_combo.currentIndexChanged.connect(self._save_prefs)
        file_action_row.addWidget(self.file_action_combo, 1)
        prefs_layout.addLayout(file_action_row)

        layout.addWidget(prefs_group)

        about_group = QGroupBox("About")
        about_layout = QVBoxLayout(about_group)
        about_browser = QTextBrowser()
        about_browser.setHtml(ABOUT_TEXT)
        about_browser.setMaximumHeight(220)
        about_layout.addWidget(about_browser)
        layout.addWidget(about_group)

        layout.addStretch(1)

    def _current_index_path_text(self) -> str:
        if not self.state.current_root:
            return "No root selected yet."
        return str(self.state.settings.index_path_for(self.state.current_root))

    def _choose_custom_index_location(self) -> None:
        if not self.state.current_root:
            QMessageBox.information(self, "No root selected", "Select a root folder on the Index Management screen first.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Choose folder to store the search index")
        if not directory:
            return
        new_path = Path(directory) / "finder_index.sqlite3"
        self.state.settings.index_paths[self.state.current_root] = str(new_path)
        self.state.settings.save()
        self.index_path_label.setText(str(new_path))
        QMessageBox.information(
            self, "Index location changed",
            "The index location has changed. Rebuild the index from the "
            "Index Management screen so it is created at the new location.",
        )
        self.state.set_root(self.state.current_root)

    def _save_prefs(self) -> None:
        self.state.settings.show_mismatch_warnings = self.show_warnings_check.isChecked()
        self.state.settings.ask_before_rebuild = self.ask_rebuild_check.isChecked()
        self.state.settings.use_ai_suggestions = self.use_ai_check.isChecked()
        self.state.settings.default_file_action = self.file_action_combo.currentData()
        self.state.settings.save()
