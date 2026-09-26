"""Pre-scan a root to estimate on-disk size and expected index footprint.

Used to show the "Indexing this folder (~X GB, ~Y files) may need ~Z MB of
free disk space" confirmation before a first index build. Bounded by a time
budget so it stays fast even on very large trees; if the budget runs out the
result is extrapolated and flagged as an estimate rather than an exact count.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from app.core.indexer import SKIP_DIR_NAMES

# Empirically-rough bytes per indexed row: files table columns + indexes +
# the FTS5 external-content row (name/path/tokens duplicated for search).
BYTES_PER_ROW_OVERHEAD = 250
FTS_MULTIPLIER = 1.6

DEFAULT_TIME_BUDGET_SECONDS = 4.0


@dataclass
class SizeEstimate:
    file_count: int
    total_bytes: int
    avg_path_len: float
    estimated_index_bytes: int
    truncated: bool  # True if the scan hit the time budget before finishing


def estimate(root, time_budget: float = DEFAULT_TIME_BUDGET_SECONDS) -> SizeEstimate:
    start = time.time()
    file_count = 0
    total_bytes = 0
    total_path_chars = 0
    truncated = False

    stack = [str(root)]
    while stack:
        if time.time() - start > time_budget:
            truncated = True
            break
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if time.time() - start > time_budget:
                        truncated = True
                        break
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in SKIP_DIR_NAMES:
                            continue
                        stack.append(entry.path)
                    else:
                        file_count += 1
                        total_path_chars += len(entry.path)
                        try:
                            total_bytes += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            pass
        except OSError:
            continue

    avg_path_len = (total_path_chars / file_count) if file_count else 40.0

    est_row_bytes = (avg_path_len * 2 + BYTES_PER_ROW_OVERHEAD) * FTS_MULTIPLIER
    estimated_index_bytes = int(file_count * est_row_bytes)

    return SizeEstimate(
        file_count=file_count,
        total_bytes=total_bytes,
        avg_path_len=avg_path_len,
        estimated_index_bytes=estimated_index_bytes,
        truncated=truncated,
    )


def format_confirmation_message(est: SizeEstimate) -> str:
    gb = est.total_bytes / (1024**3)
    mb_index = est.estimated_index_bytes / (1024**2)
    prefix = "At least " if est.truncated else ""
    return (
        f"{prefix}~{gb:.2f} GB across ~{est.file_count:,} files.\n"
        f"Indexing may require approximately {mb_index:.1f} MB of free disk space "
        f"for the search index. Continue?"
    )
