"""Optional, fully-local Named Entity Recognition (NER) used ONLY during
restructure planning, to suggest better client/employee names than plain
regex/keyword matching can find on its own.

Design constraints this module exists to satisfy:
  - No network access, ever. The model ships inside the app (bundled by
    PyInstaller); nothing is downloaded or called out to at runtime.
  - Never required. If the model package isn't installed (e.g. a dev
    environment that skipped `requirements.txt`'s model line), every public
    function here degrades to returning nothing, and callers fall back to
    the regex-only heuristic in `metadata_extractor.py`.
  - Only used where a multi-second, once-per-plan cost is acceptable: the
    Restructure wizard's preview step, which already runs on a background
    thread behind a "Computing preview…" spinner. It is deliberately NOT
    used during normal indexing/search, which must stay instant.

Model choice: spaCy's small multilingual NER model (`xx_ent_wiki_sm`,
~40MB). Its English-only sibling (`en_core_web_sm`) was tried first and
reliably missed common Indian personal names (e.g. "Ramesh Kumar", "Suresh
Sharma") that are typical in this app's CA/finance context — the
multilingual model, trained on WikiNER across many languages, recognizes
these substantially more often. Its entity spans are looser (they sometimes
swallow a neighboring doc-type/date word), so `_clean_entity_text` reuses
the same keyword/date stripping already used elsewhere in
`metadata_extractor.py` to trim them back down to just the name.
"""
from __future__ import annotations

import functools
import importlib.util

from app.core.metadata_extractor import strip_known_tokens

MODEL_NAME = "xx_ent_wiki_sm"
_NAME_LABELS = {"PER", "PERSON", "ORG", "MISC"}


@functools.lru_cache(maxsize=1)
def _load_model():
    try:
        import spacy
        return spacy.load(MODEL_NAME, disable=["parser", "lemmatizer"])
    except Exception:
        # Missing package, missing model data, incompatible spaCy version,
        # or any other load failure: NER is a bonus, never a hard dependency.
        return None


def is_available() -> bool:
    """Cheap check: are the packages present, without paying the ~1s cost of
    actually loading the model pipeline. Use this for UI status display."""
    return importlib.util.find_spec("spacy") is not None and importlib.util.find_spec(MODEL_NAME) is not None


def _clean_entity_text(raw: str, discovered_vocab: list[str] | None = None) -> str | None:
    """Strip doc-type/date/structural tokens a loose NER span may have
    swallowed, keeping only the plausible name part. `discovered_vocab` lets
    the caller pass this specific file's own detected doc type (e.g. "Nda"
    for a folder-specific category not in the fixed CA/finance keyword map),
    so a category word never leaks into the name Finder shows the user."""
    tokens = strip_known_tokens(raw, discovered_vocab)
    if not tokens:
        return None
    return " ".join(t.capitalize() for t in tokens)


def suggest_name(text: str, discovered_vocab: list[str] | None = None) -> str | None:
    """Best-effort person/organization name for `text`, or None if the model
    isn't available or found nothing usable. `text` should be a short
    filename/foldername-derived string (spaces, not underscores).

    The model is markedly better at recognizing names in title-cased text
    (confirmed empirically — "priya mehta form16 2023" finds nothing, while
    "Priya Mehta Form16 2023" correctly finds "Priya Mehta") but real
    filenames are just as often all-lowercase or ALL-CAPS, so the input is
    normalized to title case before running the model regardless of how the
    original filename was written.
    """
    nlp = _load_model()
    if nlp is None or not text.strip():
        return None

    doc = nlp(text.title())
    candidates = []
    for ent in doc.ents:
        if ent.label_ not in _NAME_LABELS:
            continue
        cleaned = _clean_entity_text(ent.text, discovered_vocab)
        if cleaned:
            candidates.append(cleaned)
    if not candidates:
        return None
    # Prefer candidates with no stray digits - a real person/company name
    # essentially never contains one, so a garbled token like "March2024"
    # (a date fragment NER mistook for an entity) should lose to a genuine
    # candidate like "Xyz Corp" even though it happens to be more
    # characters, which plain longest-string-wins would get backwards.
    digit_free = [c for c in candidates if not any(ch.isdigit() for ch in c)]
    pool = digit_free or candidates
    return max(pool, key=len)
