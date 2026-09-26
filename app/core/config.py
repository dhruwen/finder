"""Application configuration: paths, settings persistence.

Phase-2/3 note: this module is the single place that knows where app data
lives. Custom-rule config (Phase-2) and AI settings (Phase-3) should be
added as new keys in `Settings`, not new files.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


APP_NAME = "Finder"


def app_data_dir() -> Path:
    """Return the per-OS directory for app config/data (not the search index)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME.lower()


def default_index_path(root: Path) -> Path:
    """Default index DB location: hidden folder inside the indexed root."""
    return root / ".finder_index" / "index.sqlite3"


SETTINGS_FILE = "settings.json"


@dataclass
class Settings:
    roots: list[str] = field(default_factory=list)
    index_paths: dict[str, str] = field(default_factory=dict)  # root -> index db path
    show_mismatch_warnings: bool = True
    ask_before_rebuild: bool = True
    last_root: str | None = None

    @classmethod
    def load(cls) -> "Settings":
        path = app_data_dir() / SETTINGS_FILE
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def save(self) -> None:
        d = app_data_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / SETTINGS_FILE
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    def index_path_for(self, root: str) -> Path:
        custom = self.index_paths.get(root)
        if custom:
            return Path(custom)
        return default_index_path(Path(root))
