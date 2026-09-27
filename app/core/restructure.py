"""Restructure/rename planning for Type-3 (bad structure + bad naming) users.

Canonical structure (Phase-1, fixed — Phase-2 makes this user-configurable):

    <root>/Received/<Year>/<Month>/<Client_or_Employee>/<DocType>/<file>

Naming convention:

    YYYYMMDD_<Client>_<DocType>_<Description>_<Version>.<ext>

This module only *plans* changes (pure functions over already-indexed rows —
nothing touches disk here). `migration.py` executes an approved plan.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core import ner as ner_mod
from app.core.metadata_extractor import MONTH_ABBREVIATIONS, STRUCTURAL_WORDS, strip_known_tokens
from app.core.project_detection import build_project_exclusion_set, is_project_marker_dir

UNKNOWN_CLIENT = "Unknown_Client"
UNKNOWN_DOCTYPE = "Unknown_DocType"
UNKNOWN_YEAR = "Unknown_Year"

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_VERSION_PATTERN = re.compile(r"\b[vV](\d{1,2})\b|\b(final|draft)\b", re.IGNORECASE)
_WS = re.compile(r"\s+")


def sanitize_component(s: str, max_len: int = 60) -> str:
    s = _INVALID_CHARS.sub("_", s).strip(" .")
    s = _WS.sub("_", s)
    s = re.sub(r"_+", "_", s)
    if not s:
        s = "Unnamed"
    return s[:max_len]


def _extract_version(stem: str) -> str | None:
    m = _VERSION_PATTERN.search(stem)
    if not m:
        return None
    if m.group(1):
        return f"v{m.group(1)}"
    return m.group(2).capitalize()


def _description_from_stem(stem: str, client: str | None, doc_type: str | None) -> str:
    """Whatever's left of the filename after stripping recognized tokens."""
    tokens = strip_known_tokens(stem)
    if client:
        client_tokens = {t.lower() for t in re.split(r"\s+", client)}
        tokens = [t for t in tokens if t.lower() not in client_tokens]
    tokens = [t for t in tokens if t.lower() not in {"v", "ver", "version", "final", "draft"} and not t.lower().startswith("v")]
    if not tokens:
        return "Document"
    return "_".join(t.capitalize() for t in tokens[:4])


@dataclass
class PlannedChange:
    file_id: int
    old_path: str
    new_path: str
    conflict: str | None = None
    ai_assisted: bool = False


@dataclass
class RestructurePlan:
    changes: list[PlannedChange] = field(default_factory=list)
    new_folders: set[str] = field(default_factory=set)
    conflicts: int = 0
    skipped_unchanged: int = 0
    ai_available: bool = False
    ai_suggestions_used: int = 0
    # Files left untouched because they sit inside a detected software
    # project (.git, package.json, requirements.txt, node_modules, ...) —
    # restructuring never reorganizes those. See project_detection.py.
    skipped_project_files: int = 0
    root_is_project: bool = False

    @property
    def files_affected(self) -> int:
        return len(self.changes)


def _build_new_path(root: Path, row: sqlite3.Row, mode: str, client_override: str | None = None) -> Path:
    old_path = Path(row["path"])
    ext = row["extension"] or ""
    client_name = client_override or row["client_name"]
    client = sanitize_component(client_name or UNKNOWN_CLIENT)
    doc_type = sanitize_component(row["doc_type"] or UNKNOWN_DOCTYPE)
    year = row["year"]
    month = row["month"]

    if mode == "rename_only":
        new_dir = old_path.parent
    else:
        year_str = str(year) if year else UNKNOWN_YEAR
        month_str = MONTH_ABBREVIATIONS[month] if month and 1 <= month <= 12 else "Unknown_Month"
        new_dir = root / "Received" / year_str / month_str / client / doc_type

    if year and month and 1 <= month <= 12:
        date_prefix = f"{year:04d}{month:02d}01"
    elif row["modified_at"]:
        date_prefix = datetime.fromtimestamp(row["modified_at"]).strftime("%Y%m%d")
    else:
        date_prefix = "00000000"

    stem = old_path.stem
    description = _description_from_stem(stem, client_name, row["doc_type"])
    version = _extract_version(stem)

    parts = [date_prefix, client, doc_type, description]
    if version:
        parts.append(version)
    new_name = sanitize_component("_".join(parts), max_len=180) + (f".{ext}" if ext else "")
    return new_dir / new_name


def plan_restructure(
    root: Path,
    conn: sqlite3.Connection,
    mode: str = "full",
    root_key: str | None = None,
    use_ai: bool = True,
) -> RestructurePlan:
    """Build a full rename/move plan for every indexed file under `root`.

    mode: "full" (move into canonical structure and rename) or
          "rename_only" (keep current folder, rename file in place).
    use_ai: if True and a local NER model is available (see `app/core/ner.py`),
            use it to suggest better client/employee names than the plain
            regex/keyword extraction already stored on each row. Always
            falls back to the stored value when the model is unavailable or
            finds nothing usable — this never blocks planning.
    """
    assert mode in ("full", "rename_only")
    root = root.resolve()
    root_key = root_key or str(root)
    rows = conn.execute("SELECT * FROM files WHERE root = ?", (root_key,)).fetchall()

    plan = RestructurePlan()
    plan.ai_available = use_ai and ner_mod.is_available()
    used_destinations: dict[str, int] = {}
    existing_paths = {row["path"] for row in rows}

    plan.root_is_project = is_project_marker_dir(root)
    all_parent_dirs = {Path(row["parent_dir"]) for row in rows} | {root}
    project_dirs = build_project_exclusion_set(all_parent_dirs, root)

    for row in rows:
        if Path(row["parent_dir"]) in project_dirs:
            plan.skipped_project_files += 1
            continue

        client_override = None
        ai_assisted = False
        if plan.ai_available:
            old_path_probe = Path(row["path"])
            # The file's own name is the primary signal. Its parent folder's
            # name is only added as extra context when it's actually likely
            # to be meaningful (an organized client subfolder) - never the
            # selected root itself (e.g. "CA_Data", "Documents") or a
            # generic/structural folder name (e.g. "Misc", "dump"), both of
            # which would otherwise get swept into the detected name once
            # title-cased for the model (see ner.suggest_name).
            parent_name = old_path_probe.parent.name
            include_parent = (
                old_path_probe.parent != root and parent_name.lower() not in STRUCTURAL_WORDS
            )
            context_parts = [old_path_probe.stem] + ([parent_name] if include_parent else [])
            context = " ".join(context_parts).replace("_", " ")
            # This file's own detected doc type (e.g. "Nda", learned from
            # this folder's own files - see build_doc_type_vocabulary) is
            # passed so a loose NER span can't leak it into the name, even
            # when it's a category word the fixed CA/finance dictionary
            # doesn't know about.
            doc_type_hint = [row["doc_type"]] if row["doc_type"] else None
            suggestion = ner_mod.suggest_name(context, discovered_vocab=doc_type_hint)
            if suggestion and suggestion.lower() != (row["client_name"] or "").lower():
                client_override = suggestion
                ai_assisted = True
                plan.ai_suggestions_used += 1

        new_path = _build_new_path(root, row, mode, client_override)
        old_path = Path(row["path"])
        if new_path == old_path:
            plan.skipped_unchanged += 1
            continue

        key = str(new_path).lower()
        conflict = None
        if key in used_destinations:
            used_destinations[key] += 1
            stem, ext = new_path.stem, new_path.suffix
            new_path = new_path.with_name(f"{stem}__dup{used_destinations[key]}{ext}")
            conflict = "Duplicate destination name; suffix added to avoid collision"
            plan.conflicts += 1
        else:
            used_destinations[key] = 0
            if str(new_path) in existing_paths and str(new_path) != str(old_path):
                conflict = "Destination path already exists among indexed files"
                plan.conflicts += 1

        # Every ancestor folder down to (not including) root may not exist
        # yet either — e.g. for a brand-new "Received/2024/.../Audit" chain,
        # not just the deepest "Audit" folder. The exists() filter below
        # drops whichever of these turn out to already be on disk.
        ancestor = new_path.parent
        while True:
            plan.new_folders.add(str(ancestor))
            if ancestor == root or ancestor.parent == ancestor:
                break
            ancestor = ancestor.parent

        plan.changes.append(
            PlannedChange(
                file_id=row["id"], old_path=str(old_path), new_path=str(new_path),
                conflict=conflict, ai_assisted=ai_assisted,
            )
        )

    # Only count folders that don't already exist on disk.
    plan.new_folders = {f for f in plan.new_folders if not Path(f).exists()}
    return plan
