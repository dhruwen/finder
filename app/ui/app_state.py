"""Shared, in-memory application state passed to every screen.

Holds the currently-selected root, its open DB connection, and app settings.
Screens read/write this object and listen to `AppState.indexChanged` to know
when to refresh (e.g. after a (re)index or a restructure finishes).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from app.core import db as db_mod
from app.core.config import Settings


class AppState(QObject):
    indexChanged = pyqtSignal()
    rootChanged = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings.load()
        self.current_root: str | None = self.settings.last_root
        self._conn: sqlite3.Connection | None = None
        if self.current_root:
            self._open_connection(self.current_root)

    def _open_connection(self, root: str) -> None:
        if self._conn is not None:
            self._conn.close()
        index_path = self.settings.index_path_for(root)
        self._conn = db_mod.connect(index_path)

    @property
    def conn(self) -> sqlite3.Connection | None:
        return self._conn

    def set_root(self, root: str) -> None:
        root = str(Path(root).resolve())
        self.current_root = root
        self._open_connection(root)
        if root not in self.settings.roots:
            self.settings.roots.append(root)
        self.settings.last_root = root
        self.settings.save()
        self.rootChanged.emit(root)

    def notify_index_changed(self) -> None:
        self.indexChanged.emit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
