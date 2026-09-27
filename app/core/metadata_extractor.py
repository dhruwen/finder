"""Rule-based metadata extraction from file names and folder paths.

No AI. Everything here is regex + keyword-map + heuristic driven, as required
for Phase-1. Phase-2 is expected to replace the module-level constants below
with a user-editable rule set (same function signatures), so keep the public
functions' signatures stable.
"""
from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Configurable keyword maps / patterns (Phase-2: move to user-editable config)
# ---------------------------------------------------------------------------

# Not everything after the last dot in a file name is a real file extension —
# messy filenames commonly end in a version/date/status fragment instead,
# e.g. "Ramesh Audit FY22-23.v2", "GST Return.Jan.2024", "Budget.final".
# These are never treated as extensions, regardless of anything else below.
_PURE_VERSION_PATTERN = re.compile(r"^v\d{1,3}$")
_FAKE_EXTENSION_WORDS = frozenset({
    "final", "draft", "old", "new", "copy", "orig", "original",
    "rev", "revised", "updated", "backup", "signed", "unsigned",
})

# A small curated safety net on top of the much broader `mimetypes` stdlib
# database (see `normalize_extension`) — covers a few common types that
# aren't always registered there, kept intentionally short since the point
# is to NOT hand-maintain an ever-incomplete industry-specific list anymore
# (an earlier version of this allowlist was CA/finance-biased and silently
# hid real extensions like .dwg/.psd/.py for any other kind of business —
# `mimetypes` covers those broadly instead).
KNOWN_EXTENSIONS: frozenset[str] = frozenset({
    "pdf", "doc", "docx", "dot", "dotx", "rtf", "odt", "txt", "wpd",
    "xls", "xlsx", "xlsm", "xlsb", "csv", "tsv", "ods",
    "ppt", "pptx", "ppsx", "odp",
    "jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "heic", "webp",
    "zip", "rar", "7z", "tar", "gz",
    "msg", "eml", "pst",
    "xml", "json", "html", "htm",
    "mp3", "mp4", "wav", "m4a", "avi", "mov", "mkv",
    "dwg", "dxf", "psd", "ai", "indd", "cdr", "sketch", "fig",
    "py", "js", "ts", "java", "sql", "yml", "yaml", "md",
})

# A real extension is almost always short and alphanumeric starting with a
# letter (pdf, docx, mp4, 7z is the rare digit-led exception - handled via
# KNOWN_EXTENSIONS/mimetypes instead of this fallback pattern).
_PLAUSIBLE_EXTENSION_PATTERN = re.compile(r"^[a-z][a-z0-9]{0,6}$")


def normalize_extension(raw_suffix: str) -> str | None:
    """`Path.suffix`-style raw suffix (with or without leading dot) -> a real
    extension, or None if it doesn't look like one.

    Checked in order: (1) never accept a pure digit, version marker
    ("v2"), or status word ("final") — those are almost always leftover
    filename fragments, not extensions; (2) accept anything in
    `KNOWN_EXTENSIONS` or recognized by Python's built-in `mimetypes`
    database (broad, industry-agnostic coverage — CAD, design, code, media,
    documents, ...); (3) otherwise, accept it if it's still structurally
    plausible as a short extension, so a real but unlisted file type is
    never silently hidden just because no one thought to list it.
    """
    ext = raw_suffix.lower().lstrip(".")
    if not ext:
        return None
    if ext.isdigit() or _PURE_VERSION_PATTERN.match(ext) or ext in _FAKE_EXTENSION_WORDS:
        return None
    if ext in KNOWN_EXTENSIONS:
        return ext
    mime, _encoding = mimetypes.guess_type(f"file.{ext}")
    if mime is not None:
        return ext
    if _PLAUSIBLE_EXTENSION_PATTERN.match(ext):
        return ext
    return None


# Broad, domain-agnostic groupings for the File Type filter, so it reads as
# "Documents / Code / Images / ..." instead of a flat alphabetical wall of
# extensions. Fixed display order; categories with nothing in the current
# index simply aren't shown (see home_screen.py).
CATEGORY_ORDER: list[str] = [
    "Documents", "Spreadsheets", "Presentations", "Images", "Design",
    "Code", "Archives", "Email", "Audio/Video", "Other",
]

# Explicit overrides for extensions where the generic MIME-type fallback
# below would either be wrong (mimetypes reports CAD files like .dwg as
# "image/...") or too coarse (office/code formats all show up as "text" or
# "application" at the MIME top level, which isn't a useful category).
_CATEGORY_OVERRIDES: dict[str, str] = {
    "pdf": "Documents", "doc": "Documents", "docx": "Documents", "dot": "Documents",
    "dotx": "Documents", "rtf": "Documents", "odt": "Documents", "txt": "Documents",
    "wpd": "Documents", "md": "Documents", "epub": "Documents",
    "xls": "Spreadsheets", "xlsx": "Spreadsheets", "xlsm": "Spreadsheets",
    "xlsb": "Spreadsheets", "csv": "Spreadsheets", "tsv": "Spreadsheets", "ods": "Spreadsheets",
    "ppt": "Presentations", "pptx": "Presentations", "ppsx": "Presentations", "odp": "Presentations",
    "jpg": "Images", "jpeg": "Images", "png": "Images", "gif": "Images", "bmp": "Images",
    "tif": "Images", "tiff": "Images", "heic": "Images", "webp": "Images", "svg": "Images",
    "psd": "Design", "ai": "Design", "indd": "Design", "cdr": "Design",
    "sketch": "Design", "fig": "Design", "dwg": "Design", "dxf": "Design",
    "zip": "Archives", "rar": "Archives", "7z": "Archives", "tar": "Archives", "gz": "Archives",
    "msg": "Email", "eml": "Email", "pst": "Email",
    "mp3": "Audio/Video", "mp4": "Audio/Video", "wav": "Audio/Video", "m4a": "Audio/Video",
    "avi": "Audio/Video", "mov": "Audio/Video", "mkv": "Audio/Video",
    "py": "Code", "js": "Code", "ts": "Code", "java": "Code", "sql": "Code",
    "html": "Code", "htm": "Code", "xml": "Code", "json": "Code", "yml": "Code",
    "yaml": "Code", "sh": "Code", "c": "Code", "cpp": "Code", "cs": "Code",
    "go": "Code", "rs": "Code", "php": "Code", "rb": "Code",
}

# Fallback for any extension not explicitly listed above: bucket by the
# MIME type's top-level category (from `mimetypes`), so a genuinely unusual
# extension no one thought to list still lands somewhere sensible rather
# than being silently dumped in "Other".
_MIME_TOP_LEVEL_CATEGORY: dict[str, str] = {
    "image": "Images", "audio": "Audio/Video", "video": "Audio/Video",
    "text": "Documents", "message": "Email", "model": "Design",
}


def extension_category(ext: str) -> str:
    """Broad category label for a file extension (Documents, Code, Images,
    ...), for grouping the File Type filter instead of a flat list."""
    ext = ext.lower().lstrip(".")
    if ext in _CATEGORY_OVERRIDES:
        return _CATEGORY_OVERRIDES[ext]
    mime, _encoding = mimetypes.guess_type(f"file.{ext}")
    if mime:
        return _MIME_TOP_LEVEL_CATEGORY.get(mime.split("/")[0], "Other")
    return "Other"


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

# 1-indexed (index 0 unused) so `MONTH_ABBREVIATIONS[month]` works directly
# for display anywhere a month number needs to look like "Mar" instead of
# a bare, confusing digit.
MONTH_ABBREVIATIONS: list[str] = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def month_label(month: int | None) -> str:
    """1 -> "Jan", None or out-of-range -> ""."""
    if month and 1 <= month <= 12:
        return MONTH_ABBREVIATIONS[month]
    return ""

# Structural / noise words that should never be treated as a client name.
STRUCTURAL_WORDS = {
    "received", "sent", "documents", "docs", "backup", "old", "new", "final",
    "draft", "copy", "scan", "scanned", "misc", "miscellaneous", "shared",
    "downloads", "archive", "archived", "temp", "tmp", "files", "folder",
    "data", "clients", "client", "employees", "employee", "staff", "common",
    "general", "office", "personal", "work", "current", "previous", "year",
    "month", "records", "record", "attachment", "attachments", "output",
    "input", "working", "workings", "print", "signed", "unsigned",
    # Auto-generated filename prefixes from phones/cameras/screenshot tools —
    # never a person or client name, even though nothing else marks them as
    # noise (e.g. "IMG_20240315_142233.jpg" -> "Img" would otherwise become
    # the "client").
    "img", "dsc", "dscf", "pxl", "vid", "mov", "screenshot", "screen",
    "shot", "whatsapp", "photo", "picture", "untitled",
    # Other generic "everything goes here" folder names.
    "dump", "inbox", "unsorted", "stuff", "other", "others",
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
# Catches the auto-generated-prefix words above even when a camera/scanner
# glued a sequence number straight onto them with no separator ("scan0001",
# "img2024", "dsc4521") - a bare STRUCTURAL_WORDS membership check only
# catches the word alone, not word+digits as a single token.
_AUTO_GENERATED_TOKEN_PATTERN = re.compile(
    r"^(img|dsc|dscf|pxl|vid|scan|photo|picture|screenshot)\d+$", re.IGNORECASE
)


def _despace(text: str) -> str:
    """Turn separator chars that are \\w (like '_') into spaces so \\b patterns
    actually see a word boundary around dates/months embedded in filenames
    such as 'Report_2024_final.pdf'."""
    return text.replace("_", " ")


def _resolve_dd_mm(a: int, b: int) -> tuple[int, int] | None:
    """Given the two middle numbers from an ambiguous "DD-MM-YYYY or
    MM-DD-YYYY?" date fragment, return (month, day) using whichever reading
    is a valid calendar date. DD-MM is tried first (this app's primary
    convention), falling back to MM-DD when that's the only valid reading —
    e.g. "03-14-2024" can only be MM-DD (March 14), since 14 isn't a valid
    month. Returns None if neither reading is plausible, so the caller can
    fall back to treating this as not a date at all rather than storing a
    bogus month like 14 or 25.
    """
    def valid(month: int, day: int) -> bool:
        return 1 <= month <= 12 and 1 <= day <= 31

    if valid(b, a):  # DD-MM-YYYY: a=day, b=month
        return b, a
    if valid(a, b):  # MM-DD-YYYY: a=month, b=day
        return a, b
    return None


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
    if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31:
        return int(m.group(1))
    m = _DATE_DDMMYYYY.search(text)
    if m and _resolve_dd_mm(int(m.group(1)), int(m.group(2))):
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
        month, day = int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return month
    m = _DATE_DDMMYYYY.search(text)
    if m:
        resolved = _resolve_dd_mm(int(m.group(1)), int(m.group(2)))
        if resolved:
            return resolved[0]
    m = _MONTH_WORD_PATTERN.search(text)
    if m:
        return MONTH_NAMES[m.group(1).lower()]
    return None


def extract_doc_type(text: str, discovered_vocab: list[str] | None = None) -> str | None:
    """Doc-type detection: the fixed CA/finance keyword map (ITR, Audit, GST,
    ...) is checked first since those are unambiguous, well-known
    abbreviations. If nothing matches, `discovered_vocab` — category words
    learned from this specific folder's own files by
    `build_doc_type_vocabulary`, not hardcoded to any industry — is checked
    next, so document-type detection still works for folders that aren't
    CA/finance at all (legal, engineering, marketing, anything)."""
    lowered = _despace(text.lower())
    best: tuple[str, int] | None = None  # (doc_type, matched keyword length)
    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.strip() and kw.strip() in lowered:
                if best is None or len(kw) > best[1]:
                    best = (doc_type, len(kw))
    if best:
        return best[0]

    if discovered_vocab:
        matches = [v for v in discovered_vocab if v.lower() in lowered]
        if matches:
            return max(matches, key=len).title()
    return None


def strip_known_tokens(text: str, discovered_vocab: list[str] | None = None) -> list[str]:
    """Tokenize text, dropping doc-type keywords, dates, months, structural words."""
    lowered = _despace(text.lower())
    # Longest keyword first: "gst return" must be stripped whole before the
    # shorter "gst" gets a chance to eat only part of it and leave "return"
    # behind as a stray word (e.g. "gst_return_ramesh" -> bare "return").
    for keywords in DOC_TYPE_KEYWORDS.values():
        for kw in sorted(keywords, key=len, reverse=True):
            lowered = lowered.replace(kw, " ")
    for v in sorted(discovered_vocab or [], key=len, reverse=True):
        lowered = lowered.replace(v.lower(), " ")
    lowered = _FY_PATTERN.sub(" ", lowered)
    lowered = _DATE_YYYYMMDD.sub(" ", lowered)
    lowered = _DATE_DDMMYYYY.sub(" ", lowered)
    lowered = _YEAR_PATTERN.sub(" ", lowered)
    lowered = _MONTH_WORD_PATTERN.sub(" ", lowered)
    tokens = [t for t in _TOKEN_SPLIT.split(lowered) if t]
    tokens = [
        t for t in tokens
        if t not in STRUCTURAL_WORDS
        and not t.isdigit()
        and len(t) > 1
        and not _AUTO_GENERATED_TOKEN_PATTERN.match(t)
    ]
    return tokens


def extract_client(
    text: str, known_clients: list[str] | None = None, discovered_doc_types: list[str] | None = None
) -> str | None:
    """Best-effort client/person name extraction.

    Strategy: if a list of known client names (built by `build_known_clients`)
    is supplied, match against it first (case-insensitive substring). Otherwise
    fall back to picking the longest leftover token(s) after stripping
    doc-type/date/structural noise (including any auto-discovered doc-type
    words, so a category word never gets mistaken for a client name).
    """
    if known_clients:
        lowered = _despace(text.lower())
        matches = [c for c in known_clients if _despace(c.lower()) in lowered]
        if matches:
            return max(matches, key=len)

    tokens = strip_known_tokens(text, discovered_doc_types)
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


def build_doc_type_vocabulary(
    entries: list[tuple[str, str]],
    known_clients: list[str] | None = None,
    min_doc_frequency: int = 2,
    min_spread: int = 2,
    max_vocab: int = 25,
) -> list[str]:
    """Learn candidate document-type/category words directly from this
    folder's own files, instead of relying on a fixed industry keyword list
    (the `DOC_TYPE_KEYWORDS` map only covers CA/finance terms like ITR/GST).
    This is the same "learn from the data, don't hardcode an industry" idea
    already used for `build_known_clients`, applied to document categories —
    so doc-type detection also works for legal, engineering, marketing, or
    any other corporate file structure.

    `entries` is a list of (file_stem, parent_folder_name) pairs collected
    during a scan. A token is treated as a category word (like "Invoice",
    "Contract", "Drawing") rather than a one-off description word if it:
      - appears in at least `min_doc_frequency` different files, AND
      - appears across at least `min_spread` different parent folders — i.e.
        it repeats as a stable label across different people/projects/
        clients, not just as part of one person's own naming quirk.

    If the whole tree is one flat folder (no subfolders to spread across),
    the spread requirement is relaxed to frequency alone, since there is
    nothing to discriminate against in that case.
    """
    token_files: dict[str, set[int]] = {}
    token_contexts: dict[str, set[str]] = {}
    client_tokens: set[str] = set()
    for c in known_clients or []:
        client_tokens.update(_despace(c.lower()).split())

    all_contexts: set[str] = set()
    for i, (stem, parent) in enumerate(entries):
        context = _despace((parent or "").strip().lower()) or "?"
        all_contexts.add(context)
        tokens = {t for t in strip_known_tokens(stem or "") if len(t) >= 3} - client_tokens
        for t in tokens:
            token_files.setdefault(t, set()).add(i)
            token_contexts.setdefault(t, set()).add(context)

    effective_min_spread = min_spread if len(all_contexts) >= min_spread else 1
    candidates = [
        t
        for t, files in token_files.items()
        if len(files) >= min_doc_frequency and len(token_contexts[t]) >= effective_min_spread
    ]
    candidates.sort(key=lambda t: len(token_files[t]), reverse=True)
    return [t.title() for t in candidates[:max_vocab]]


def extract_all(
    text: str,
    known_clients: list[str] | None = None,
    discovered_doc_types: list[str] | None = None,
) -> ExtractedMetadata:
    return ExtractedMetadata(
        client_name=extract_client(text, known_clients, discovered_doc_types),
        doc_type=extract_doc_type(text, discovered_doc_types),
        year=extract_year(text),
        month=extract_month(text),
    )


def tokenize_path(path: str) -> list[str]:
    """Split a path into folder-name segments (for building the client vocabulary)."""
    return [p for p in path.replace("\\", "/").split("/") if p]
