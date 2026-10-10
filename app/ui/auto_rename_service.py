"""Watches the folders listed in Settings.auto_rename_rules and renames
newly-added files to each folder's naming convention (app/core/auto_rename.py
decides the name; this module only watches and renames).

Safety rules, in line with the rest of the app:
  - Only files that are genuinely *new* are touched. A file the user renames
    or moves around inside a watched folder keeps its inode, which was
    already seen, so it's left alone — Finder never fights a manual rename.
  - Partial downloads (.crdownload, .part, ...), hidden files and Office
    lock files are ignored, and a file is only renamed once its size has
    stopped changing.
  - Files stay in the folder they were added to; only the name changes.
    Software-project folders are skipped (see project_detection.py).
  - Every rename is logged (app data dir / auto_rename_log.csv) and can be
    undone from Settings -> Auto-rename.

Only runs while Finder is open: files added while it's closed aren't
picked up until they're touched again.
"""
from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal

from app.core import auto_rename as ar
from app.core.config import Settings, app_data_dir
from app.core.indexer import SKIP_DIR_NAMES
from app.core.project_detection import is_project_marker_dir

LOG_FILE = "auto_rename_log.csv"
MAX_WATCHED_DIRS = 2000
SETTLE_SECONDS = 2.0


@dataclass
class RenameEvent:
    old_path: str
    new_path: str
    timestamp: float
    undone: bool = False


@dataclass
class _Rule:
    folder: Path
    pattern: str
    include_subfolders: bool
    vocab: ar.FolderVocabulary | None = None
    tree_pattern: ar.NamingPattern | None = None
    tree_pattern_learned: bool = False


class AutoRenameService(QObject):
    renamed = pyqtSignal(object)  # RenameEvent
    failed = pyqtSignal(str)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.history: list[RenameEvent] = []
        self._rules: list[_Rule] = []
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)
        self._snapshots: dict[str, dict[str, int]] = {}  # dir -> {file name: inode}
        self._known_inodes: set[tuple[int, int]] = set()  # (st_dev, st_ino)
        self._pending: dict[str, tuple[int, float]] = {}  # path -> (size, first seen)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._process_pending)
        self.reload()

    # -- configuration ------------------------------------------------------------
    def reload(self) -> None:
        """(Re)start watching per the current Settings.auto_rename_rules."""
        if self._watcher.directories():
            self._watcher.removePaths(self._watcher.directories())
        self._snapshots.clear()
        self._pending.clear()
        self._rules = [
            _Rule(Path(r["folder"]), r.get("pattern") or ar.AUTO, bool(r.get("include_subfolders", True)))
            for r in self.settings.auto_rename_rules
            if r.get("enabled", True) and Path(r["folder"]).is_dir()
        ]
        for rule in self._rules:
            self._watch_tree(rule.folder, rule.include_subfolders)
        if self._rules:
            self._timer.start()
        else:
            self._timer.stop()

    def is_watched(self, folder: str) -> bool:
        return any(
            r.get("enabled", True) and Path(r["folder"]) == Path(folder)
            for r in self.settings.auto_rename_rules
        )

    def set_rule(self, folder: str, enabled: bool = True, pattern: str = ar.AUTO, include_subfolders: bool = True) -> None:
        rules = [r for r in self.settings.auto_rename_rules if Path(r["folder"]) != Path(folder)]
        rules.append({
            "folder": str(Path(folder)), "pattern": pattern,
            "include_subfolders": include_subfolders, "enabled": enabled,
        })
        self.settings.auto_rename_rules = rules
        self.settings.save()
        self.reload()

    def remove_rule(self, folder: str) -> None:
        self.settings.auto_rename_rules = [
            r for r in self.settings.auto_rename_rules if Path(r["folder"]) != Path(folder)
        ]
        self.settings.save()
        self.reload()

    # -- watching ---------------------------------------------------------------
    def _watch_tree(self, folder: Path, recursive: bool, initial: bool = True) -> None:
        dirs = [folder]
        if recursive:
            for dirpath, dirnames, _ in os.walk(folder, onerror=lambda e: None):
                dirnames[:] = [d for d in dirnames if self._should_descend(d)]
                dirs.extend(Path(dirpath) / d for d in dirnames)
                if len(dirs) >= MAX_WATCHED_DIRS:
                    break
        for d in dirs[:MAX_WATCHED_DIRS]:
            self._watch_dir(d, initial)

    @staticmethod
    def _should_descend(name: str) -> bool:
        # Safari's in-progress "x.pdf.download" is a folder; never look inside.
        return not (name in SKIP_DIR_NAMES or name.startswith(".") or name.lower().endswith(ar.TEMP_SUFFIXES))

    def _watch_dir(self, d: Path, initial: bool) -> None:
        """`initial`: files already here when watching started are the
        folder's existing state, never renamed. Otherwise (a folder that
        appeared later, e.g. a client folder dropped in) its files are new."""
        key = str(d)
        if key in self._snapshots or len(self._snapshots) >= MAX_WATCHED_DIRS:
            return
        self._snapshots[key] = self._list_files(d, remember=initial)
        self._watcher.addPath(key)
        if not initial:
            for name in self._snapshots[key]:
                self._consider_new(d / name)

    def _list_files(self, d: Path, remember: bool) -> dict[str, int]:
        files: dict[str, int] = {}
        try:
            entries = list(os.scandir(d))
        except OSError:
            return files
        for e in entries:
            try:
                if not e.is_file(follow_symlinks=False):
                    continue
                # os.stat, not DirEntry.stat: on Windows the latter leaves
                # st_ino/st_dev as 0, which would make every file look the
                # same and break "don't rename what the user renamed".
                st = os.stat(e.path, follow_symlinks=False)
            except OSError:
                continue
            files[e.name] = st.st_ino
            # Temp files' inodes are deliberately NOT remembered: Chrome and
            # Firefox finish a download by renaming "x.crdownload" -> "x.pdf"
            # (same inode), and that finished file must still count as new.
            if remember and not ar.is_ignorable(e.name):
                self._known_inodes.add((st.st_dev, st.st_ino))
        return files

    def _rule_for(self, path: Path) -> _Rule | None:
        best = None
        for rule in self._rules:
            if path.parent == rule.folder or (rule.include_subfolders and rule.folder in path.parents):
                if best is None or len(rule.folder.parts) > len(best.folder.parts):
                    best = rule
        return best

    def _on_directory_changed(self, dir_path: str) -> None:
        d = Path(dir_path)
        if not d.is_dir():
            self._snapshots.pop(dir_path, None)
            return
        before = self._snapshots.get(dir_path, {})
        now = self._list_files(d, remember=False)
        self._snapshots[dir_path] = now

        for name in now.keys() - before.keys():
            self._consider_new(d / name)

        # New subfolders get watched too (e.g. a new client folder).
        rule = self._rule_for(d / "_")
        if rule and rule.include_subfolders:
            try:
                for e in os.scandir(d):
                    if e.is_dir(follow_symlinks=False) and self._should_descend(e.name):
                        self._watch_tree(Path(e.path), recursive=True, initial=False)
            except OSError:
                pass

    def _consider_new(self, path: Path) -> None:
        if ar.is_ignorable(path.name):
            return
        try:
            st = path.stat()
        except OSError:
            return
        ident = (st.st_dev, st.st_ino)
        if ident in self._known_inodes:
            return  # renamed/moved by the user (or by us) — leave it
        self._known_inodes.add(ident)
        self._pending[str(path)] = (st.st_size, time.time())

    # -- renaming -----------------------------------------------------------------
    def _process_pending(self) -> None:
        now = time.time()
        for key, (size, first_seen) in list(self._pending.items()):
            path = Path(key)
            try:
                current = path.stat().st_size
            except OSError:
                self._pending.pop(key, None)  # gone again (temp file, moved away)
                continue
            if current != size:
                self._pending[key] = (current, now)  # still being written
                continue
            if now - first_seen < SETTLE_SECONDS:
                continue
            self._pending.pop(key, None)
            self._rename_new_file(path)

    def _rename_new_file(self, path: Path) -> None:
        rule = self._rule_for(path)
        if rule is None or is_project_marker_dir(path.parent):
            return
        if rule.vocab is None:
            rule.vocab = ar.build_folder_vocabulary(rule.folder)
        if rule.pattern == ar.AUTO and not rule.tree_pattern_learned:
            rule.tree_pattern = ar.learn_tree_pattern(rule.folder, rule.vocab)
            rule.tree_pattern_learned = True

        pending_names = {Path(p).name for p in self._pending if Path(p).parent == path.parent}
        pattern = ar.pattern_for_folder(
            path.parent, rule.pattern, rule.vocab, fallback=rule.tree_pattern,
            exclude=pending_names | {path.name},
        )
        new_name = ar.propose_name(path, rule.folder, pattern, rule.vocab)
        if not new_name:
            return
        target = ar.unique_target(path.parent, new_name)
        try:
            os.rename(path, target)
        except OSError as e:
            self.failed.emit(f"Couldn't rename {path.name}: {e}")
            return
        event = RenameEvent(str(path), str(target), time.time())
        self.history.append(event)
        self._log(event, "renamed")
        self.renamed.emit(event)

    def undo(self, event: RenameEvent) -> bool:
        """Put a file back under its original name (same folder)."""
        new, old = Path(event.new_path), Path(event.old_path)
        if event.undone or not new.exists() or old.exists():
            return False
        try:
            os.rename(new, old)  # same inode, so the watcher ignores it
        except OSError as e:
            self.failed.emit(f"Couldn't undo rename of {new.name}: {e}")
            return False
        event.undone = True
        self._log(event, "undone")
        return True

    def _log(self, event: RenameEvent, status: str) -> None:
        path = app_data_dir() / LOG_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            is_new = not path.exists()
            with path.open("a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if is_new:
                    writer.writerow(["timestamp", "status", "old_path", "new_path"])
                writer.writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    status, event.old_path, event.new_path,
                ])
        except OSError:
            pass  # logging must never break renaming

    @staticmethod
    def log_path() -> Path:
        return app_data_dir() / LOG_FILE
