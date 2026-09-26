"""Rule-based metadata extraction from file names and folder paths.

No AI. Everything here is regex + keyword-map + heuristic driven, as required
for Phase-1. Phase-2 is expected to replace the module-level constants below
with a user-editable rule set (same function signatures), so keep the public
functions' signatures stable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Configurable keyword maps / patterns (Phase-2: move to user-editable config)
# ---------------------------------------------------------------------------

DOC_TYPE_KEYWORDS: dict[str, list[str]] = {
    "ITR": ["itr", "income tax return", "incometax return", "itr-v", "itrv"],
    "Audit": ["audit", "audited", "audit report", "tax audit", "3ca", "3cb", "3cd"],
    "GST": ["gst", "gstr", "gst return"],
    "TDS": ["tds", "form 26as", "26as"],
    "Salary": ["salary", "payslip", "pay slip", "salary slip", "payroll"],
    "Form16": ["form 16", "form16", "form-16"],
    "Balance Sheet": ["balance sheet", "balancesheet", "bs"],
    "P&L": ["profit and loss", "profit & loss", "p&l", "pnl", "p&amp;l"],
    "Bank Statement": ["bank statement", "bank stmt", "bankstatement"],
    "Invoice": ["invoice", "inv no", "bill"],
    "Report": ["report", "mis report", "monthly report", "annual report"],
    "PAN": ["pan card", "pan-card", " pan "],
    "Agreement": ["agreement", "contract", "moU", "mou"],
    "Ledger": ["ledger"],
    "Receipt": ["receipt", "acknowledgement", "acknowledgment"],
}

MONTH_NAMES: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# Structural / noise words that should never be treated as a client name.
STRUCTURAL_WORDS = {
    "received", "sent", "documents", "docs", "backup", "old", "new", "final",
    "draft", "copy", "scan", "scanned", "misc", "miscellaneous", "shared",
    "downloads", "archive", "archived", "temp", "tmp", "files", "folder",
    "data", "clients", "client", "employees", "employee", "staff", "common",
    "general", "office", "personal", "work", "current", "previous", "year",
    "month", "records", "record", "attachment", "attachments", "output",
    "input", "working", "workings", "print", "signed", "unsigned",
}

_FY_PATTERN = re.compile(
    r"\bFY[\s\-]?(\d{2,4})[\s\-/]?(\d{2,4})?\b", re.IGNORECASE
)
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
_DATE_YYYYMMDD = re.compile(r"\b(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})\b")
_DATE_DDMMYYYY = re.compile(r"\b(\d{2})[-_./](\d{2})[-_./](20\d{2}|\d{2})\b")
_MONTH_WORD_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(MONTH_NAMES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+")


def _despace(text: str) -> str:
    """Turn separator chars that are \\w (like '_') into spaces so \\b patterns
    actually see a word boundary around dates/months embedded in filenames
    such as 'Report_2024_final.pdf'."""
    return text.replace("_", " ")


def _normalize_fy_year(y1: str, y2: str | None) -> int:
    """FY23-24 or FY2023-24 -> 2024 (the ending/assessment year)."""
    def full(y: str) -> int:
        y = y.strip()
        if len(y) == 2:
            return 2000 + int(y)
        return int(y)

    if y2:
        return full(y2)
    return full(y1)


@dataclass
class ExtractedMetadata:
    client_name: str | None = None
    doc_type: str | None = None
    year: int | None = None
    month: int | None = None


def extract_year(text: str) -> int | None:
    text = _despace(text)
    m = _FY_PATTERN.search(text)
    if m:
        return _normalize_fy_year(m.group(1), m.group(2))
    m = _DATE_YYYYMMDD.search(text)
    if m:
        return int(m.group(1))
    m = _DATE_DDMMYYYY.search(text)
    if m:
        y = m.group(3)
        return int(y) if len(y) == 4 else 2000 + int(y)
    m = _YEAR_PATTERN.search(text)
    if m:
        return int(m.group(0))
    return None


def extract_month(text: str) -> int | None:
    text = _despace(text)
    m = _DATE_YYYYMMDD.search(text)
    if m:
        return int(m.group(2))
    m = _DATE_DDMMYYYY.search(text)
    if m:
        return int(m.group(2))
    m = _MONTH_WORD_PATTERN.search(text)
    if m:
        return MONTH_NAMES[m.group(1).lower()]
    return None


def extract_doc_type(text: str) -> str | None:
    lowered = text.lower()
    best: tuple[str, int] | None = None  # (doc_type, matched keyword length)
    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.strip() and kw.strip() in lowered:
                if best is None or len(kw) > best[1]:
                    best = (doc_type, len(kw))
    return best[0] if best else None


def strip_known_tokens(text: str) -> list[str]:
    """Tokenize text, dropping doc-type keywords, dates, months, structural words."""
    lowered = _despace(text.lower())
    for keywords in DOC_TYPE_KEYWORDS.values():
        for kw in keywords:
            lowered = lowered.replace(kw, " ")
    lowered = _FY_PATTERN.sub(" ", lowered)
    lowered = _DATE_YYYYMMDD.sub(" ", lowered)
    lowered = _DATE_DDMMYYYY.sub(" ", lowered)
    lowered = _YEAR_PATTERN.sub(" ", lowered)
    lowered = _MONTH_WORD_PATTERN.sub(" ", lowered)
    tokens = [t for t in _TOKEN_SPLIT.split(lowered) if t]
    tokens = [t for t in tokens if t not in STRUCTURAL_WORDS and not t.isdigit() and len(t) > 1]
    return tokens


def extract_client(text: str, known_clients: list[str] | None = None) -> str | None:
    """Best-effort client/person name extraction.

    Strategy: if a list of known client names (built by `build_known_clients`)
    is supplied, match against it first (case-insensitive substring). Otherwise
    fall back to picking the longest leftover token(s) after stripping
    doc-type/date/structural noise.
    """
    if known_clients:
        lowered = _despace(text.lower())
        matches = [c for c in known_clients if _despace(c.lower()) in lowered]
        if matches:
            return max(matches, key=len)

    tokens = strip_known_tokens(text)
    if not tokens:
        return None
    # Prefer the longest token as the client-name candidate.
    tokens.sort(key=len, reverse=True)
    return tokens[0].title()


def build_known_clients(folder_names: list[str], min_occurrences: int = 1) -> list[str]:
    """Derive a candidate client-name vocabulary from folder names in a tree.

    A folder name is a client candidate if it is not a structural word, not a
    pure doc-type keyword, and not purely numeric/date-like.
    """
    counts: dict[str, int] = {}
    for name in folder_names:
        lowered = name.strip().lower()
        if not lowered or lowered in STRUCTURAL_WORDS:
            continue
        if extract_doc_type(lowered) and lowered in [
            kw for kws in DOC_TYPE_KEYWORDS.values() for kw in kws
        ]:
            continue
        if _YEAR_PATTERN.fullmatch(lowered) or _FY_PATTERN.fullmatch(lowered):
            continue
        if lowered.isdigit():
            continue
        counts[name.strip()] = counts.get(name.strip(), 0) + 1
    return sorted([n for n, c in counts.items() if c >= min_occurrences], key=len, reverse=True)


def extract_all(text: str, known_clients: list[str] | None = None) -> ExtractedMetadata:
    return ExtractedMetadata(
        client_name=extract_client(text, known_clients),
        doc_type=extract_doc_type(text),
        year=extract_year(text),
        month=extract_month(text),
    )


def tokenize_path(path: str) -> list[str]:
    """Split a path into folder-name segments (for building the client vocabulary)."""
    return [p for p in path.replace("\\", "/").split("/") if p]
