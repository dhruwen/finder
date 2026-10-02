"""Auto-rename: keep a watched folder's naming convention for new files.

The user never has to write a naming rule. For each watched folder Finder
*learns* the convention its existing files already follow (e.g.
"20240301_Ramesh_ITR_Notes.pdf" -> `{date}_{client}_{doctype}_{description}`)
and renames any newly-added file to match, filling the slots from the new
file's own name plus the folder it landed in (a scan dropped into
".../Ramesh/ITR/" picks up "Ramesh" and "ITR" from the path). A custom
pattern can still be set per folder when the learned one isn't right.

Pure functions only — nothing here watches the filesystem or renames
anything on disk; see `app/ui/auto_rename_service.py` for that.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.metadata_extractor import (
    DOC_TYPE_KEYWORDS,
    MONTH_ABBREVIATIONS,
    MONTH_NAMES,
    build_doc_type_vocabulary,
    build_known_clients,
    extract_all,
    extract_doc_type,
)
from app.core.restructure import _description_from_stem, _extract_version, sanitize_component

# "auto" = learn from the folder's existing files; anything else is a
# user-written template using the tokens below.
AUTO = "auto"
DEFAULT_TEMPLATE = "{date}_{client}_{doctype}_{description}_{version}"
TOKENS = ("date", "year", "month", "client", "doctype", "description", "version")
TOKEN_HELP = {
    "date": "YYYYMMDD (from the file name, else the file's modified date)",
    "year": "4-digit year",
    "month": "3-letter month, e.g. Mar",
    "client": "person / client name",
    "doctype": "document type, e.g. ITR, Invoice",
    "description": "what's left of the original name",
    "version": "v2 / Final / Draft, if present",
}

# Files that are still being written, OS/app junk, or lock files.
TEMP_SUFFIXES = (".crdownload", ".part", ".partial", ".download", ".tmp", ".temp", ".opdownload", ".!ut")
IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", "Icon\r"}

_TOKEN_RE = re.compile(r"\{(" + "|".join(TOKENS) + r")\}")
_SEPARATORS = ("_", "-", " ")
_DATE8 = re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$")
_YEAR4 = re.compile(r"^(19|20)\d{2}$")
_VERSION = re.compile(r"^(v\d{1,3}|final|draft)$", re.IGNORECASE)

MIN_LEARN_SAMPLES = 3
MIN_LEARN_SHARE = 0.6


@dataclass(frozen=True)
class NamingPattern:
    template: str
    # "upper" | "lower" | "title" | "keep" — applied to filled-in text slots
    # (not literals) so learned conventions like "ramesh_itr_..." stay
    # lowercase.
    case: str = "keep"
    learned: bool = False


def is_ignorable(name: str) -> bool:
    """Hidden files, temp/partial downloads, and Office lock files."""
    return (
        name in IGNORED_NAMES
        or name.startswith(".")
        or name.startswith("~$")
        or name.lower().endswith(TEMP_SUFFIXES)
    )


# -- learning ---------------------------------------------------------------
def _pick_separator(stems: list[str]) -> str:
    counts = Counter()
    for stem in stems:
        for sep in _SEPARATORS:
            counts[sep] += stem.count(sep)
    sep, n = counts.most_common(1)[0] if counts else ("_", 0)
    return sep if n else "_"


def _is_doc_type_word(part: str, doc_vocab: list[str] | None) -> bool:
    low = part.lower()
    if any(low == v.lower() for v in doc_vocab or []):
        return True
    return any(
        low == name.lower().replace(" ", "") or low in (k.strip() for k in keywords)
        for name, keywords in DOC_TYPE_KEYWORDS.items()
    )


def _classify(part: str, client: str | None, doc_vocab: list[str] | None, used: set[str]) -> str:
    """Map one name segment to a template token, or "" for free text. Each
    of client/doctype is taken at most once (`used`); later look-alikes
    stay part of the description."""
    low = part.lower()
    if _DATE8.match(part):
        token = "{date}"
    elif _YEAR4.match(part):
        token = "{year}"
    elif low in MONTH_NAMES:
        token = "{month}"
    elif _VERSION.match(part):
        token = "{version}"
    elif client and low == client.lower().replace(" ", ""):
        token = "{client}"
    elif _is_doc_type_word(part, doc_vocab):
        token = "{doctype}"
    else:
        return ""
    if token in used:
        return ""
    used.add(token)
    return token


def _case_of(words: list[str]) -> str:
    alpha = [w for w in words if any(c.isalpha() for c in w)]
    if not alpha:
        return "keep"
    if all(w.islower() for w in alpha):
        return "lower"
    if all(w.isupper() for w in alpha):
        return "upper"
    if all(w[:1].isupper() for w in alpha):
        return "title"
    return "keep"


def learn_pattern(
    stems: list[str],
    known_clients: list[str] | None = None,
    doc_vocab: list[str] | None = None,
) -> NamingPattern | None:
    """Infer the naming convention shared by `stems` (file names without
    extension), or None if there isn't a consistent one.

    Each name is split on the folder's dominant separator and every segment
    classified as a date/year/month/client/doctype/version slot or free text
    (runs of free text collapse into one `{description}` slot). The most
    common resulting shape wins if it covers most of the files. A free-text
    slot that is the *same word* in every matching file (e.g. an "INV"
    prefix) is kept as a literal instead of a description.
    """
    stems = [s for s in stems if s]
    if len(stems) < MIN_LEARN_SAMPLES:
        return None
    sep = _pick_separator(stems)

    samples: list[tuple[tuple[str, ...], list[str]]] = []
    for stem in stems:
        parts = [p for p in stem.split(sep) if p]
        if not parts:
            continue
        client = extract_all(stem.replace(sep, " "), known_clients, doc_vocab).client_name
        shape: list[str] = []
        texts: list[str] = []
        used: set[str] = set()
        for part in parts:
            token = _classify(part, client, doc_vocab, used)
            if token == "{version}":
                continue  # optional everywhere; re-added below
            if token:
                shape.append(token)
                texts.append("")
            elif shape and shape[-1] == "{description}":
                texts[-1] += sep + part
            else:
                shape.append("{description}")
                texts.append(part)
        samples.append((tuple(shape), texts))

    def fits(shape: tuple[str, ...], candidate: tuple[str, ...]) -> bool:
        # A trailing description absorbs whatever follows it, so
        # "..._GST_Return_Jan" still fits "{date}_{client}_{doctype}_{description}".
        if shape == candidate:
            return True
        return (
            bool(candidate) and candidate[-1] == "{description}"
            and len(shape) >= len(candidate) and shape[: len(candidate)] == candidate
        )

    candidates = {shape for shape, _ in samples}
    if not candidates:
        return None
    best_shape = max(candidates, key=lambda c: (sum(fits(s, c) for s, _ in samples), len(c)))
    members = [texts for shape, texts in samples if fits(shape, best_shape)]
    if len(members) < MIN_LEARN_SAMPLES or len(members) / len(samples) < MIN_LEARN_SHARE:
        return None
    structured = {"{date}", "{year}", "{month}", "{client}", "{doctype}"}
    if not structured.intersection(best_shape):
        return None  # no real convention, just free-form names

    slots = list(best_shape)
    for i, token in enumerate(slots):
        if token == "{description}" and i < len(slots) - 1:
            values = {m[i].lower() for m in members}
            if len(values) == 1:
                slots[i] = members[0][i]  # literal shared by every file, e.g. "INV"
    slots.append("{version}")

    words = [w for m in members for w in m if w]
    return NamingPattern(template=sep.join(slots), case=_case_of(words), learned=True)


# -- rendering ----------------------------------------------------------------
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_ALWAYS_REQUIRED = {"date", "year"}


def _template_sep(template: str) -> str:
    literal = _TOKEN_RE.sub("", template)
    counts = Counter(c for c in literal if c in _SEPARATORS)
    return counts.most_common(1)[0][0] if counts else "_"


def _apply_case(value: str, case: str) -> str:
    if case == "lower":
        return value.lower()
    if case == "upper":
        return value.upper()
    if case == "title":
        return "".join(w[:1].upper() + w[1:] for w in re.split(r"([^A-Za-z0-9]+)", value))
    return value


def render(pattern: NamingPattern, values: dict[str, str]) -> str:
    """Fill `pattern` with `values`. Empty slots disappear along with the
    separator next to them, so "{date}_{client}_{doctype}" with no client
    gives "20240301_ITR", not "20240301__ITR"."""
    sep = _template_sep(pattern.template)

    def fill(m: re.Match) -> str:
        token = m.group(1)
        value = values.get(token) or ""
        if sep != "_":
            value = value.replace("_", sep)
        if token not in ("date", "year", "version"):
            value = _apply_case(value, pattern.case)
        return value

    out = _TOKEN_RE.sub(fill, pattern.template)
    out = re.sub(re.escape(sep) + "{2,}", sep, out).strip(sep)
    out = _INVALID_CHARS.sub("_", out).strip(" .")
    return out[:180]


def template_regex(pattern: NamingPattern) -> re.Pattern:
    """A regex matching names that already follow `pattern`, so a file that
    Finder (or the user) already named correctly is left alone. Match it
    against `sep + stem` (see `conforms`): every item carries its leading
    separator, which lets optional slots vanish cleanly."""
    sep = _template_sep(pattern.template)
    items: list[tuple[str, bool]] = []  # (regex, is_token)
    for piece in re.split(r"(\{\w+\})", pattern.template):
        m = _TOKEN_RE.fullmatch(piece)
        if m:
            items.append((m.group(1), True))
        else:
            items.extend((re.escape(w), False) for w in piece.split(sep) if w)

    # With no date/year/literal to anchor on, any name would match a bare
    # "{client}_{description}" — so then every slot (except version) is
    # required instead of optional.
    anchored = any(not is_tok or val in _ALWAYS_REQUIRED for val, is_tok in items)
    token_re = {
        "date": r"\d{8}", "year": r"\d{4}", "month": r"[A-Za-z]{3,9}",
        "version": r"(?:[vV]\d{1,3}|[Ff]inal|FINAL|[Dd]raft|DRAFT)",
    }
    out = ""
    for val, is_tok in items:
        body = token_re.get(val, r".+?") if is_tok else val
        optional = is_tok and (val == "version" or (anchored and val not in _ALWAYS_REQUIRED))
        out += f"(?:{re.escape(sep)}{body})" + ("?" if optional else "")
    return re.compile(r"^" + out + r"$", re.IGNORECASE if pattern.case != "keep" else 0)


def conforms(stem: str, pattern: NamingPattern) -> bool:
    return bool(template_regex(pattern).match(_template_sep(pattern.template) + stem))


# -- folder context -------------------------------------------------------------
@dataclass
class FolderVocabulary:
    known_clients: list[str]
    doc_types: list[str]


def build_folder_vocabulary(folder: Path, max_files: int = 20000) -> FolderVocabulary:
    """Client and doc-type vocabularies for a watched folder, learned the
    same way the indexer does (see indexer._collect_tree_info)."""
    dir_names: list[str] = []
    entries: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(folder, onerror=lambda e: None):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        dir_names.extend(dirnames)
        parent = Path(dirpath).name
        entries.extend((Path(f).stem, parent) for f in filenames if not is_ignorable(f))
        if len(entries) >= max_files:
            break
    clients = build_known_clients(dir_names)
    return FolderVocabulary(clients, build_doc_type_vocabulary(entries, clients))


def values_for(path: Path, watch_root: Path, vocab: FolderVocabulary) -> dict[str, str]:
    """Slot values for a new file: from its own name first, then from the
    folders it sits in under the watched root (like the indexer does)."""
    stem = path.stem
    name_meta = extract_all(stem, vocab.known_clients, vocab.doc_types)
    try:
        rel = path.parent.relative_to(watch_root)
        folder_text = " / ".join([watch_root.name, *rel.parts])
    except ValueError:
        folder_text = path.parent.name
    folder_meta = extract_all(folder_text, vocab.known_clients, vocab.doc_types)
    # Folder names like "Personal" or "Downloads" shouldn't become a client
    # just because the fallback picks the longest leftover word — only trust
    # a folder-derived client when it's a known folder-name client.
    folder_client = folder_meta.client_name if folder_meta.client_name in vocab.known_clients else None

    # A known client (a real folder name in this tree) beats the extractor's
    # longest-leftover-word guess, so "echallan.pdf" dropped into ".../John/"
    # is filed under John rather than under a client called "Echallan".
    name_client = name_meta.client_name
    if name_client in vocab.known_clients or not folder_client:
        client = name_client or folder_client
    else:
        client = folder_client
    doc_type = name_meta.doc_type or folder_meta.doc_type or extract_doc_type(folder_text, vocab.doc_types)
    year = name_meta.year or folder_meta.year
    month = name_meta.month or folder_meta.month

    if name_meta.year and name_meta.month:
        date = f"{year:04d}{month:02d}01"
    else:
        try:
            date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y%m%d")
        except OSError:
            date = datetime.now().strftime("%Y%m%d")
        year = year or int(date[:4])
        month = month or int(date[4:6])

    description = _description_from_stem(stem, client, doc_type)
    if description == "Document" and doc_type:
        description = ""  # placeholder only; the doc type already says it
    return {
        "date": date,
        "year": str(year) if year else "",
        "month": MONTH_ABBREVIATIONS[month] if month and 1 <= month <= 12 else "",
        "client": sanitize_component(client) if client else "",
        "doctype": sanitize_component(doc_type) if doc_type else "",
        "description": description,
        "version": _extract_version(stem) or "",
    }


def propose_name(
    path: Path, watch_root: Path, pattern: NamingPattern, vocab: FolderVocabulary
) -> str | None:
    """New file name (with extension) for `path`, or None to leave it as is."""
    if conforms(path.stem, pattern):
        return None
    stem = render(pattern, values_for(path, watch_root, vocab))
    if not stem or stem == path.stem:
        return None
    return stem + path.suffix.lower()


def unique_target(directory: Path, name: str) -> Path:
    target = directory / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 2
    while target.exists():
        target = directory / f"{stem}_{n}{suffix}"
        n += 1
    return target


def pattern_for_folder(
    directory: Path,
    configured: str,
    vocab: FolderVocabulary,
    fallback: NamingPattern | None = None,
    exclude: set[str] | None = None,
) -> NamingPattern:
    """The pattern to apply to a new file in `directory`: the user's custom
    template if set, else the convention learned from that folder's
    existing files, else `fallback` (learned across the whole watched tree),
    else Finder's standard naming."""
    if configured and configured != AUTO:
        return NamingPattern(template=configured)
    exclude = exclude or set()
    try:
        stems = [
            Path(e.name).stem for e in os.scandir(directory)
            if e.is_file() and e.name not in exclude and not is_ignorable(e.name)
        ]
    except OSError:
        stems = []
    learned = learn_pattern(stems, vocab.known_clients, vocab.doc_types)
    return learned or fallback or NamingPattern(template=DEFAULT_TEMPLATE)


def learn_tree_pattern(root: Path, vocab: FolderVocabulary, max_files: int = 2000) -> NamingPattern | None:
    """Convention shared across the whole watched tree — used for a new or
    empty subfolder that has no files of its own to learn from yet."""
    stems: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        stems.extend(Path(f).stem for f in filenames if not is_ignorable(f))
        if len(stems) >= max_files:
            break
    return learn_pattern(stems, vocab.known_clients, vocab.doc_types)


def example_for(pattern: NamingPattern) -> str:
    """A sample rendered name, for showing the user what a template does."""
    sample = {
        "date": "20240315", "year": "2024", "month": "Mar", "client": "Ramesh",
        "doctype": "ITR", "description": "Acknowledgement", "version": "v2",
    }
    return render(pattern, sample) + ".pdf"
