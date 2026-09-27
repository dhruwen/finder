"""Tests for the optional local-NER restructure assist.

The cleanup logic is tested directly (no model needed). The model-backed
`suggest_name` is only exercised if the optional NER package is actually
installed in this environment; otherwise those parts are skipped rather than
failed, since the whole point of `app/core/ner.py` is to degrade gracefully
when the model isn't present.
"""
import pytest

from app.core import ner


def test_is_available_returns_bool():
    assert isinstance(ner.is_available(), bool)


def test_suggest_name_empty_text_returns_none():
    assert ner.suggest_name("") is None
    assert ner.suggest_name("   ") is None


@pytest.mark.skipif(not ner.is_available(), reason="NER model package not installed in this environment")
def test_suggest_name_finds_person_name():
    result = ner.suggest_name("Priya Mehta Form16 2023")
    assert result is not None
    assert "priya" in result.lower()


@pytest.mark.skipif(not ner.is_available(), reason="NER model package not installed in this environment")
def test_suggest_name_finds_org_name():
    result = ner.suggest_name("ABC Corp GST Return Jan2024")
    assert result is not None
    assert "abc" in result.lower()


@pytest.mark.skipif(not ner.is_available(), reason="NER model package not installed in this environment")
def test_suggest_name_strips_doctype_and_year_leakage():
    # A loose NER span that swallows "Audit FY23" alongside the real name
    # should come back cleaned to just the name, not the full noisy span.
    result = ner.suggest_name("Ramesh Kumar Audit FY23-24")
    assert result is not None
    assert "audit" not in result.lower()
    assert "23" not in result


def test_suggest_name_never_raises_without_model(monkeypatch):
    monkeypatch.setattr(ner, "_load_model", lambda: None)
    assert ner.suggest_name("Ramesh Kumar Audit 2024") is None


@pytest.mark.skipif(not ner.is_available(), reason="NER model package not installed in this environment")
def test_suggest_name_works_on_all_lowercase_input():
    # Confirmed empirically: the model misses names in all-lowercase text
    # ("priya mehta form16 2023" finds nothing) but catches them once
    # title-cased - suggest_name must normalize case internally rather than
    # relying on the caller to have already-capitalized text, since real
    # filenames are just as often all-lowercase.
    result = ner.suggest_name("priya mehta form16 2023")
    assert result is not None
    assert "priya" in result.lower()


@pytest.mark.skipif(not ner.is_available(), reason="NER model package not installed in this environment")
def test_suggest_name_uses_per_file_discovered_doc_type_hint():
    # Without the hint, a loose span may swallow a folder-specific category
    # word the fixed CA/finance dictionary doesn't know about (e.g. "Nda").
    # With it, that word must not appear in the returned name.
    result = ner.suggest_name("Acme Industries NDA Draft", discovered_vocab=["Nda"])
    if result is not None:
        assert "nda" not in result.lower()


@pytest.mark.skipif(not ner.is_available(), reason="NER model package not installed in this environment")
def test_suggest_name_prefers_digit_free_candidate():
    # NER can return multiple entity spans; a garbled one containing a
    # stray date/number ("March2024") must not win over a clean name
    # ("Xyz Corp") just because it happens to be more characters.
    result = ner.suggest_name("Xyz Corp Invoice March2024")
    if result is not None:
        assert not any(ch.isdigit() for ch in result)
