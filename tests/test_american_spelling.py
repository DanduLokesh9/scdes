"""Everything a person reads is in American English.

The client asked for it on 2026-09-24 — "organization v organisation". The
build specification is written in British English, so copying its wording
verbatim is how a British spelling gets back in; this is what catches it.

Checked: every prose string literal in app/*.py, and the screen scripts and
page. Not checked, on purpose: identifiers, keys and stored option values
(`organisation_type`, `finalises`, "licence"), which stored data depends on;
the reference agency's own quoted documents; and the typo list, which
explains that British spellings in what a person types are never flagged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import _americanize as am

ROOT = Path(__file__).resolve().parent.parent / "app"
PY = sorted(p for p in ROOT.glob("*.py") if p.name not in am.SKIP)
WEB = sorted([*(ROOT / "web" / "assets").glob("*.js"), ROOT / "web" / "index.html"])


@pytest.mark.parametrize("path", PY, ids=lambda p: p.name)
def test_no_british_spelling_in_python_prose(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    found = [(w, text.strip()[:70]) for _, _, text in am.python_prose(source)
             for w in am.british_words(text)]
    assert not found, found[:5]


@pytest.mark.parametrize("path", WEB, ids=lambda p: p.name)
def test_no_british_spelling_on_the_screens(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    assert am.convert_markup(source) == source, \
        sorted(set(am.british_words(source)) - {"organisation", "finalises"})[:10]


def test_keys_and_stored_values_are_left_alone() -> None:
    """A lowercase one-word string is a key or a stored value, never prose."""
    src = 'x = {"finalises": 1, "licence": "The licence or subscription"}\n'
    assert am.convert_python(src) == \
        'x = {"finalises": 1, "licence": "The license or subscription"}\n'
    js = 'const o = { organisation: v }; d.colour; "organisation"; say("Your organisation");'
    assert am.convert_markup(js) == \
        'const o = { organisation: v }; d.colour; "organisation"; say("Your organization");'


def test_words_that_are_american_too_are_never_rewritten() -> None:
    for word in ("advise", "exercise", "enterprise", "surprise", "revise",
                 "promise", "analysis", "otherwise"):
        assert am.convert(word) == word
