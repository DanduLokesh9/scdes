"""The Discretion Register — what an agency gets to decide, and what it does not.

Most of what this file defends is the client's method rather than code: classify
every sentence first, never invent alternatives, show the reference setting as
the visible default. Those are the rules a future section-mining pass has to keep
to, and a test is the only form of them that survives someone new doing the work.

Two rulings get their own tests because they were close calls and the client
overturned the first reading:

  · "No autonomous decision system is authorized" is **configurable**, with the
    consequence stated and accepted — not structural, as the miner first had it;
  · whether the framework is a public document is **not** configurable.
"""

from __future__ import annotations

import re

import pytest

from app import discretion


def _rows():
    return [r for s in discretion.SECTIONS for r in s.rows]


def _row(key: str):
    row = next((r for r in _rows() if r.key == key), None)
    assert row is not None, f"no register row called {key!r}"
    return row


# ------------------------------------------------------------- the method

def test_every_row_carries_the_phrase_that_produced_it() -> None:
    """The user has to be able to see what in their own document prompted it."""
    for row in _rows():
        assert row.source_phrase, f"{row.key} has no source phrase"


def test_every_row_is_classified() -> None:
    for row in _rows():
        assert row.classification in discretion.CLASSIFICATIONS, row.key


def test_structural_rows_say_why_and_ask_nothing() -> None:
    """"Not configurable, and here is why" is what earns trust in the blanks
    that are configurable."""
    for row in _rows():
        if row.classification == "STRUCTURAL":
            assert row.why_fixed, f"{row.key} refuses without explaining"
            assert not row.question, f"{row.key} is fixed but asks a question"
            assert not row.configurable


def test_configurable_rows_ask_a_question_and_show_the_default() -> None:
    for row in _rows():
        if row.configurable:
            assert row.question, f"{row.key} is configurable but asks nothing"
            assert row.default, f"{row.key} has no visible default"
            assert row.answer_format in discretion.FORMATS, row.key


def test_no_row_invents_alternatives_it_cannot_source() -> None:
    """Offering three made-up options where the source offers one is how a
    template starts writing an agency's policy for it."""
    for row in _rows():
        if row.options:
            assert row.default in row.options or row.answer_format == "select", (
                f"{row.key}: the reference setting is not among the options, so "
                f"the options were not drawn from the source")


def test_citation_and_time_bound_rows_carry_a_refresh_trigger() -> None:
    """A cited authority that nothing re-checks is out of date the moment it
    moves."""
    for row in _rows():
        if row.classification in ("CITATION", "TIME-BOUND"):
            assert row.refresh_trigger, f"{row.key} will silently go stale"


# ------------------------------------ the client's ruling on autonomous systems

def test_autonomous_decisions_are_the_agencys_choice() -> None:
    """Client: "It's configurable. If an agency wants that, they are free to do
    so." A framework that forbids what an agency already does is one they will
    quietly ignore."""
    row = _row("definitions.autonomous")
    assert row.configurable
    assert row.classification == "POSTURE"
    assert row.answer_format == "accept-risk"


def test_choosing_it_requires_accepting_a_named_consequence() -> None:
    """Client: "a big warning and accept risk to proceed flag"."""
    row = _row("definitions.autonomous")
    assert row.requires_acceptance
    assert row.warning
    assert len(row.abrogates) >= 2, (
        '"there are risks" is not a consequence anyone can weigh — the claims '
        "that stop being true have to be named")
    assert any("human" in a.lower() for a in row.abrogates)


def test_the_safe_answer_is_the_default() -> None:
    """Client: "the goal is to encourage the human in authority"."""
    row = _row("definitions.autonomous")
    assert "person reviews" in row.default.lower()
    assert row.options[0] == row.default, "the default is offered first"


def test_publication_is_not_on_the_table() -> None:
    """Client: "they do not get to choose if the framework is a public
    document"."""
    row = _row("definitions.publication")
    assert not row.configurable
    assert row.classification == "STRUCTURAL"
    assert "public" in row.why_fixed.lower()


# ------------------------------------------------- the client's ruling on numbers

def test_numeric_calibrations_confirm_a_default_rather_than_offering_a_slider() -> None:
    """Client accepted this: "Sliders invite fiddling with numbers that carry
    real consequences."

    A weight or a threshold is a confirm-default, never free text and never a
    slider.

    The detection was "the question mentions a weight, or the default contains a
    digit anywhere". That was fine while only Sections 1–3 existed and wrong as
    soon as 4–13 were mined: it flagged "Section 504 of the Rehabilitation Act",
    "WCAG 2.1 Level AA", "Level 1, Level 2, Level 3" and "Category 1" — a
    citation, a standard, and two sets of labels, none of them a number anybody
    calibrates. Narrowed to what the rule is actually about: a magnitude, which
    is a default that is a bare number or a number with a unit.

    Deliberately still catches the case that matters. A row defaulting to "1.5"
    or "30 days" with a free-text box fails here.
    """
    assert discretion.NUMERIC_ANSWER_FORMAT == "confirm-default"
    assert "slider" not in " ".join(discretion.FORMATS).lower()

    numeric_hints = ("weight", "threshold", "score", "percent", "how many")
    # A magnitude standing on its own: "1.5", "18", "30 days", "72 hours".
    magnitude = re.compile(
        r"^\s*\d+(\.\d+)?\s*(%|days?|hours?|weeks?|months?|years?|points?)?\s*$",
        re.IGNORECASE)

    for row in _rows():
        if not row.configurable:
            continue
        looks_numeric = (any(h in row.question.lower() for h in numeric_hints)
                         or bool(magnitude.match(row.default)))
        if looks_numeric and row.answer_format not in ("confirm-default",
                                                       "accept-risk", "select"):
            pytest.fail(f"{row.key} calibrates a number with "
                        f"{row.answer_format!r}; use "
                        f"{discretion.NUMERIC_ANSWER_FORMAT!r}")


def test_a_bare_magnitude_in_free_text_is_still_caught() -> None:
    """Guards the narrowing above. If the detection is loosened again to the
    point where this passes, the rule has stopped doing anything."""
    import re as _re
    magnitude = _re.compile(
        r"^\s*\d+(\.\d+)?\s*(%|days?|hours?|weeks?|months?|years?|points?)?\s*$",
        _re.IGNORECASE)
    for value in ("1.5", "18", "30 days", "72 hours", "80%"):
        assert magnitude.match(value), f"{value} must read as a magnitude"
    for value in ("Level 1, Level 2, Level 3", "WCAG 2.1 Level AA",
                  "Section 504 of the Rehabilitation Act", "Low, Moderate, High"):
        assert not magnitude.match(value), f"{value} is a label, not a magnitude"


# ---------------------------------------------------------------- honesty

def test_unmined_sections_say_so_rather_than_appearing_empty() -> None:
    """A section reading "not yet mined" is honest in a way that a silently
    missing section is not."""
    for section in discretion.SECTIONS:
        if not section.mined:
            assert not section.rows
            assert section.purpose, (
                f"section {section.number} is unmined and also unexplained")


def test_the_whole_framework_is_listed_even_where_it_is_unfinished() -> None:
    numbers = [s.number for s in discretion.SECTIONS]
    assert numbers == [str(n) for n in range(1, 14)]


def test_keys_are_unique() -> None:
    keys = [r.key for r in _rows()]
    assert len(keys) == len(set(keys))
