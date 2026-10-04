"""Writes restructure reports to disk: an interactive HTML page and a PDF
(rendered with Qt's own text engine — no extra dependencies), plus the
raw CSV log. Content comes from app/core/report.py."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QMarginsF, QSizeF
from PyQt6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from app.core import report
from app.core.migration import MigrationResult, write_report


@dataclass
class ReportFiles:
    html: Path
    pdf: Path
    csv: Path
    data: report.ReportData


def write_pdf(html: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Unit.Millimeter)
    writer.setResolution(96)
    writer.setTitle("Restructure report")
    writer.setCreator("Finder")

    doc = QTextDocument()
    doc.setHtml(html)
    # Lay the document out at the page's printable width (in the writer's
    # 96-dpi device pixels) so text wraps to the page instead of shrinking.
    rect = writer.pageLayout().paintRectPixels(writer.resolution())
    doc.setPageSize(QSizeF(rect.width(), rect.height()))
    doc.print(writer)
    return path


def write_all(
    root: str, results: list[MigrationResult], new_folders: set[str] | None, reports_dir: Path
) -> ReportFiles:
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    data = report.build_report(root, results, new_folders)
    reports_dir.mkdir(parents=True, exist_ok=True)

    html_path = reports_dir / f"Restructure_Report_{stamp}.html"
    html_path.write_text(report.render_interactive_html(data), encoding="utf-8")
    pdf_path = write_pdf(report.render_print_html(data), reports_dir / f"Restructure_Report_{stamp}.pdf")
    csv_path = write_report(results, reports_dir / f"migration_{stamp}.csv", fmt="csv")
    return ReportFiles(html_path, pdf_path, csv_path, data)
