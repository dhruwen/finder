"""Moderate-level "possibly misplaced file" detection.

Compares metadata inferred from the file name against metadata inferred from
its folder path. A significant disagreement (both sides confidently extracted
something, and it differs) is flagged with a human-readable reason. This never
blocks indexing or search — it only annotates rows for the Warnings screen.
"""
from __future__ import annotations

from app.core.metadata_extractor import ExtractedMetadata


def detect_mismatch(
    name_meta: ExtractedMetadata, folder_meta: ExtractedMetadata | None
) -> tuple[bool, str | None]:
    if folder_meta is None:
        return False, None

    reasons: list[str] = []

    if name_meta.client_name and folder_meta.client_name:
        a, b = name_meta.client_name.lower(), folder_meta.client_name.lower()
        if a != b and a not in b and b not in a:
            reasons.append(
                f"Folder suggests client '{folder_meta.client_name}', "
                f"file name suggests '{name_meta.client_name}'"
            )

    if name_meta.doc_type and folder_meta.doc_type and name_meta.doc_type != folder_meta.doc_type:
        reasons.append(
            f"Folder suggests document type '{folder_meta.doc_type}', "
            f"file name suggests '{name_meta.doc_type}'"
        )

    if name_meta.year and folder_meta.year and name_meta.year != folder_meta.year:
        reasons.append(
            f"Folder suggests year {folder_meta.year}, file name suggests {name_meta.year}"
        )

    if not reasons:
        return False, None
    return True, "; ".join(reasons)
