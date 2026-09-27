"""Emoji-based icons for file categories and structural nodes.

No icon asset files to bundle/ship — emoji render natively and consistently
enough across Windows/macOS/Linux for this purpose, and they make tree/list
views scannable at a glance for non-technical users without reading every
label (a folder "looks like" a folder, a spreadsheet "looks like" a
spreadsheet).
"""
from __future__ import annotations

from app.core.metadata_extractor import extension_category

FOLDER_ICON = "📁"
AI_BADGE = "✨"

CATEGORY_ICONS: dict[str, str] = {
    "Documents": "📄",
    "Spreadsheets": "📊",
    "Presentations": "📽️",
    "Images": "🖼️",
    "Design": "🎨",
    "Code": "💻",
    "Archives": "🗄️",
    "Email": "✉️",
    "Audio/Video": "🎬",
    "Other": "📦",
}


def file_icon(extension: str | None) -> str:
    if not extension:
        return CATEGORY_ICONS["Other"]
    return CATEGORY_ICONS.get(extension_category(extension), CATEGORY_ICONS["Other"])


def category_icon(category: str) -> str:
    return CATEGORY_ICONS.get(category, CATEGORY_ICONS["Other"])
