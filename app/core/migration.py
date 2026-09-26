"""Executes an approved RestructurePlan: moves/renames files, logs a report.

Nothing here runs without an explicit, already-confirmed plan. Every
operation is re-validated to stay inside the selected root before touching
disk. Dry-run mode does everything except the actual filesystem operation, so
the same code path produces the same report for preview and real runs.
"""
from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from app.core.restructure import RestructurePlan

ProgressCallback = Callable[[int, int, str], None]


@dataclass
class MigrationResult:
    old_path: str
    new_path: str
    timestamp: float
    status: str  # "success" | "error" | "skipped" | "dry_run"
    error: str | None = None


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def apply_plan(
    plan: RestructurePlan,
    conn: sqlite3.Connection,
    root: Path,
    dry_run: bool = False,
    progress_cb: ProgressCallback | None = None,
) -> list[MigrationResult]:
    root = root.resolve()
    results: list[MigrationResult] = []
    total = len(plan.changes)

    for i, change in enumerate(plan.changes, start=1):
        old_path = Path(change.old_path)
        new_path = Path(change.new_path)
        now = time.time()

        if not _is_within(root, old_path) or not _is_within(root, new_path):
            results.append(
                MigrationResult(str(old_path), str(new_path), now, "error", "Refused: path outside selected root")
            )
        elif dry_run:
            results.append(MigrationResult(str(old_path), str(new_path), now, "dry_run"))
        elif not old_path.exists():
            results.append(MigrationResult(str(old_path), str(new_path), now, "error", "Source file no longer exists"))
        else:
            try:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(new_path))
                conn.execute(
                    "UPDATE files SET path=?, name=?, parent_dir=? WHERE id=?",
                    (str(new_path), new_path.name, str(new_path.parent), change.file_id),
                )
                results.append(MigrationResult(str(old_path), str(new_path), now, "success"))
            except OSError as e:
                results.append(MigrationResult(str(old_path), str(new_path), now, "error", str(e)))

        if progress_cb:
            progress_cb(i, total, str(old_path))

    if not dry_run:
        conn.commit()
    return results


def write_report(results: list[MigrationResult], report_path: Path, fmt: str = "csv") -> Path:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        report_path.write_text(
            json.dumps([asdict(r) for r in results], indent=2, default=str), encoding="utf-8"
        )
    else:
        with report_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["old_path", "new_path", "timestamp", "status", "error"])
            writer.writeheader()
            for r in results:
                writer.writerow(asdict(r))
    return report_path


def summarize(results: list[MigrationResult]) -> dict:
    summary = {"success": 0, "error": 0, "skipped": 0, "dry_run": 0}
    for r in results:
        summary[r.status] = summary.get(r.status, 0) + 1
    return summary
