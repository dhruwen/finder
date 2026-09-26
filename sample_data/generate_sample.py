"""Creates a small sample folder demonstrating a messy (Type-3) CA/finance
file structure, for trying out indexing, search, and restructuring.

Usage:
    python sample_data/generate_sample.py [target_dir]

Default target: ./sample_data/Sample_Messy_Folder
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES: dict[str, str] = {
    # path relative to target root -> dummy content
    "stuff/johnitr24.pdf": "dummy ITR content for John, FY2023-24",
    "stuff/john_salary_mar2024.xlsx": "dummy salary slip",
    "stuff2/ABC Corp/abc_audit_2023_final.pdf": "dummy audit report",
    "stuff2/ABC Corp/abc_gst_return_jan2024.pdf": "dummy GST return",
    "Received/2024/John/John_ITR_2024.pdf": "well-organized duplicate for comparison",
    "Misc/old_backup/xyz invoice 12-03-2022.docx": "dummy invoice",
    "Misc/scan0001.pdf": "unnamed scan, no metadata in name",
    "Downloads/Priya Mehta - Form16 2023.pdf": "dummy form16",
    "Downloads/priya_bankstatement_feb2024.pdf": "dummy bank statement",
    "Client Files/Ramesh/ramesh audit fy22-23 v2.pdf": "dummy versioned audit",
    "Client Files/Ramesh/ramesh_ITR_2022.pdf": "mismatch demo: folder says Ramesh, year 2022 file in 2023 folder",
}

# Deliberately mismatched folder vs filename, for the Warnings screen demo.
MISMATCH_FILES: dict[str, str] = {
    "Received/2024/Ramesh/Suresh_Audit_2023.pdf": "folder says Ramesh/2024, filename says Suresh/2023",
}


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "Sample_Messy_Folder"
    target.mkdir(parents=True, exist_ok=True)

    for rel_path, content in {**FILES, **MISMATCH_FILES}.items():
        full = target / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    print(f"Sample folder created at: {target}")
    print(f"Files created: {len(FILES) + len(MISMATCH_FILES)}")


if __name__ == "__main__":
    main()
